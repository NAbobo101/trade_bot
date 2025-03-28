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
# exchange.verbose = True  # Ative para debug detalhado

symbols = ['BTC/USDT', 'ETH/USDT']
risk_per_trade = 0.05
timeframe = '5m'
log_file_path = "trades_log.txt"
ordens_abertas_por_simbolo = set()

# ======================== LOG UTILITÁRIO ========================
def log(mensagem):
    agora = datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')
    log_msg = f"[{agora}] {mensagem}"
    print(log_msg)
    with open(log_file_path, "a", encoding="utf-8") as f:
        f.write(log_msg + "\n")

# ======================== SYNC TEMPO ========================
def sincronizar_tempo():
    try:
        exchange.load_time_difference()
        log("⏳ Tempo sincronizado com a exchange.")
    except Exception:
        log("⚠ Erro ao sincronizar tempo: " + traceback.format_exc())

# ======================== SALDO USDT ========================
def obter_saldo_usdt():
    try:
        balance = exchange.fetch_balance()
        usdt_balance = balance['free'].get('USDT', 0)
        log(f"💰 Saldo atual em USDT: {usdt_balance:.2f}")
        return usdt_balance
    except Exception:
        log("⚠ Erro ao obter saldo USDT: " + traceback.format_exc())
        return 0

# ======================== OHLCV ========================
def obter_ohlcv(symbol, timeframe='1m', limit=300):
    try:
        return exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    except Exception:
        log(f"⚠ Erro ao obter OHLCV de {symbol}")
        return []

# ======================== ATR ========================
def calcular_atr(ohlcv, period=14):
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['H-L'] = df['high'] - df['low']
    df['H-PC'] = abs(df['high'] - df['close'].shift(1))
    df['L-PC'] = abs(df['low'] - df['close'].shift(1))
    df['TR'] = df[['H-L', 'H-PC', 'L-PC']].max(axis=1)
    atr = df['TR'].rolling(window=period).mean().iloc[-1]
    return round(atr, 4) if not np.isnan(atr) else None

# ======================== BACKTEST ========================
def backtest_simples(df, sl_pct=0.005, tp_pct=0.01):
    capital = 1000
    trades = []
    entrou = 0

    for i in range(200, len(df) - 50):
        row = df.iloc[i]
        ema50 = row['EMA50']
        ema200 = row['EMA200']
        preco_entrada = row['close']

        if ema50 > ema200:
            entrou += 1
            sl = preco_entrada * (1 - sl_pct)
            tp = preco_entrada * (1 + tp_pct)
            future = df.iloc[i+1:i+51]

            for _, fut in future.iterrows():
                if fut['low'] <= sl:
                    capital *= (1 - sl_pct)
                    trades.append('loss')
                    break
                elif fut['high'] >= tp:
                    capital *= (1 + tp_pct)
                    trades.append('win')
                    break

    if not trades:
        log(f"📉 Backtest detectou {entrou} oportunidades, mas nenhum trade atingiu SL/TP.")
        return 0, 0, 0

    taxa_acerto = trades.count('win') / len(trades) * 100
    lucro_pct = ((capital - 1000) / 1000) * 100
    return len(trades), taxa_acerto, lucro_pct

# ======================== EXCEL ========================
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

# ======================== ORDENS ABERTAS ========================
def verificar_ordens_abertas():
    try:
        log("🔍 Verificando ordens abertas existentes...")
        for symbol in symbols:
            market = exchange.market(symbol)
            if market.get("spot", False):
                params = {"category": "spot"}
            elif market.get("linear", False):
                params = {"category": "linear"}
            else:
                params = {"category": "linear"}

            ordens = exchange.fetch_open_orders(symbol, params=params)

            if ordens:
                ordens_abertas_por_simbolo.add(symbol)
                log(f"📌 Ordem aberta detectada para {symbol}. Ignorando esse par até que seja resolvido.")
            else:
                log(f"✅ Nenhuma ordem aberta para {symbol}.")
    except Exception:
        log("⚠ Erro ao verificar ordens abertas:\n" + traceback.format_exc())

# ======================== COMPRA (VERSÃO SIMPLIFICADA) ========================
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

    except Exception as e:
        log(f"⚠ Erro na ordem de compra para {symbol}:\n{str(e)}")
