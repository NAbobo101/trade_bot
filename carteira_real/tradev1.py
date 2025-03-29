import ccxt
import time
import os
import pandas as pd
import traceback
import numpy as np
import openpyxl
from datetime import datetime, UTC

# ======================== LEITURA DE CREDENCIAIS ========================
def obter_credenciais():
    caminho_credenciais = "credenciais.txt"

    if not os.path.exists(caminho_credenciais):
        print("🔐 Primeira execução detectada. Insira suas credenciais da API da Bybit.")
        api_key = input("Digite sua API Key: ").strip()
        api_secret = input("Digite seu Secret Key: ").strip()

        with open(caminho_credenciais, "w", encoding="utf-8") as f:
            f.write(f"{api_key}\n{api_secret}\n")
        print("✅ Credenciais salvas com sucesso.")
    else:
        with open(caminho_credenciais, "r", encoding="utf-8") as f:
            linhas = f.readlines()
            api_key = linhas[0].strip()
            api_secret = linhas[1].strip()

    return api_key, api_secret

# ================== CONFIGURAÇÃO DA EXCHANGE ====================
api_key, api_secret = obter_credenciais()

exchange = ccxt.bybit({
    'apiKey': api_key,
    'secret': api_secret,
    'enableRateLimit': True,
    'timeout': 30000,
    'options': {
        'adjustForTimeDifference': True,
        'defaultType': 'spot',
    },
})

USE_SANDBOX = False
exchange.set_sandbox_mode(USE_SANDBOX)
exchange.load_markets()

symbols = ['BTC/USDT', 'ETH/USDT']
risk_per_trade = 0.05
timeframe = '5m'
log_file_path = "trades_log.txt"
ordens_abertas_por_simbolo = set()
posicoes_abertas = {}
contador_logs = {symbol: 0 for symbol in symbols}
trailing_stops = {}  # Novo: controle do trailing stop

# ======================== LOG UTILITÁRIO ========================
def log(mensagem):
    agora = datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')
    log_msg = f"[{agora}] {mensagem}"
    print(log_msg)
    with open(log_file_path, "a", encoding="utf-8") as f:
        f.write(log_msg + "\n")

# ======================== CALCULAR ATR ========================
def calcular_atr(ohlcv, period=14):
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['H-L'] = df['high'] - df['low']
    df['H-PC'] = abs(df['high'] - df['close'].shift(1))
    df['L-PC'] = abs(df['low'] - df['close'].shift(1))
    df['TR'] = df[['H-L', 'H-PC', 'L-PC']].max(axis=1)
    atr = df['TR'].rolling(window=period).mean().iloc[-1]
    return round(atr, 4) if not np.isnan(atr) else None

# ======================== REGISTRO EM EXCEL ========================
def registrar_trade_excel(symbol, tipo, qtd, preco, ema50, ema200, atr, sl, tp):
    arquivo = "trades.xlsx"
    dados = {
        'Data': datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S'),
        'Par': symbol,
        'Tipo': tipo,
        'Quantidade': qtd,
        'Preço': preco,
        'EMA50': ema50,
        'EMA200': ema200,
        'ATR': atr,
        'Stop-Loss': sl,
        'Take-Profit': tp
    }
    df = pd.DataFrame([dados])
    if os.path.exists(arquivo):
        with pd.ExcelWriter(arquivo, engine='openpyxl', mode='a', if_sheet_exists='overlay') as writer:
            df.to_excel(writer, sheet_name='Trades', index=False, header=False,
                        startrow=writer.sheets['Trades'].max_row)
    else:
        df.to_excel(arquivo, sheet_name='Trades', index=False)

# ======================== VERIFICAR TRAILING STOP ========================
def verificar_trailing_stop(symbol, preco_atual):
    if symbol not in trailing_stops:
        return False

    trailing = trailing_stops[symbol]
    entrada = trailing['entrada']
    melhor_preco = trailing['melhor']
    distancia_pct = 0.005  # 0.5%

    if preco_atual > melhor_preco:
        trailing['melhor'] = preco_atual
    elif preco_atual < melhor_preco * (1 - distancia_pct):
        return True

    return False

# ======================== VENDA ========================
def executar_ordem_venda(symbol, preco):
    try:
        base = symbol.split("/")[0]
        saldo = exchange.fetch_balance()
        qtd = saldo['free'].get(base, 0)

        if qtd == 0:
            log(f"⚠ Sem saldo disponível para venda de {base}.")
            return

        order = exchange.create_market_sell_order(symbol, qtd)
        preco_venda = order.get('average') or order.get('price') or preco

        log(f"📤 VENDA {symbol} | Qtd: {qtd} | Preço Médio: {preco_venda} | Ordem ID: {order['id']}")

        if symbol in ordens_abertas_por_simbolo:
            ordens_abertas_por_simbolo.remove(symbol)
        if symbol in posicoes_abertas:
            del posicoes_abertas[symbol]
        if symbol in trailing_stops:
            del trailing_stops[symbol]

    except Exception as e:
        log(f"⚠ Erro na ordem de venda para {symbol}:\n{str(e)}")

# ======================== COMPRA ========================
def executar_ordem_compra(symbol, qtd, preco, ema50, ema200, atr, sl, tp):
    try:
        if symbol in ordens_abertas_por_simbolo:
            log(f"⚠ Ordem já aberta para {symbol}. Ignorando nova entrada.")
            return

        order = exchange.create_market_buy_order(symbol, qtd)
        preco_pago = order.get('average') or order.get('price') or preco

        log(f"💰 COMPRA {symbol} | Qtd: {qtd} | Preço Médio: {preco_pago} | Ordem ID: {order['id']}")

        registrar_trade_excel(symbol, 'buy', qtd, preco_pago, ema50, ema200, atr, sl, tp)
        ordens_abertas_por_simbolo.add(symbol)
        posicoes_abertas[symbol] = {"qtd": qtd, "preco_entrada": preco_pago}
        trailing_stops[symbol] = {"entrada": preco_pago, "melhor": preco_pago}

    except Exception as e:
        log(f"⚠ Erro na ordem de compra para {symbol}:\n{str(e)}")

# ======================== ESTRATÉGIA ========================
def estrategia_scalping_com_backtest():
    log("🚀 Iniciando estratégia Scalping com controle de tendência e lucro")
    while True:
        try:
            saldo_usdt = exchange.fetch_balance()['free'].get('USDT', 0)
            for symbol in symbols:
                ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=300)
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['EMA50'] = df['close'].ewm(span=50).mean()
                df['EMA200'] = df['close'].ewm(span=200).mean()
                preco_atual = df['close'].iloc[-1]

                log(f"🔍 Analisando {symbol} | Preço atual: {preco_atual:.2f}")

                if verificar_trailing_stop(symbol, preco_atual):
                    log(f"📉 Trailing Stop ativado para {symbol}. Realizando venda.")
                    executar_ordem_venda(symbol, preco_atual)
                    continue

                ema50 = df['EMA50'].iloc[-1]
                ema200 = df['EMA200'].iloc[-1]
                if ema50 > ema200 and symbol not in posicoes_abertas:
                    atr = calcular_atr(ohlcv[-100:], period=14)
                    tp_pct = 0.01
                    sl_pct = 0.005
                    sl = round(preco_atual * (1 - sl_pct), 2)
                    tp = round(preco_atual * (1 + tp_pct), 2)
                    qtd = round((saldo_usdt * risk_per_trade) / preco_atual, 6)

                    log(f"🧠 Sinal de COMPRA identificado para {symbol}")
                    executar_ordem_compra(symbol, qtd, preco_atual, ema50, ema200, atr, sl, tp)
                else:
                    contador_logs[symbol] += 1
                    if contador_logs[symbol] % 5 == 0:
                        log(f"⏸️ Nenhum sinal confirmado para {symbol}. Aguardando oportunidade...")

            time.sleep(60)

        except Exception:
            log("🔥 Erro na estratégia:\n" + traceback.format_exc())
            time.sleep(60)

# ======================== EXECUÇÃO ========================
if __name__ == "__main__":
    estrategia_scalping_com_backtest()
