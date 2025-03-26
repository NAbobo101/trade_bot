import ccxt
import time
import os
import pandas as pd
import traceback
import numpy as np
import openpyxl
from datetime import datetime, UTC

# ================== CONFIGURAÇÃO DA EXCHANGE ====================
exchange = ccxt.bybit({
    'apiKey': 'ljaJqxO57RRzP7YswI',
    'secret': 'uzFYCAaTa5wudw2nnaVPcITTrYmGoX1AgdTb',
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

# ======================== COMPRA ========================
def executar_ordem_compra(symbol, qtd, preco, ema50, ema200, atr, sl, tp):
    try:
        if not all([symbol, qtd, preco]):
            raise ValueError("❌ Parâmetros inválidos para criação da ordem.")

        if symbol in ordens_abertas_por_simbolo:
            log(f"⚠ Ordem já aberta anteriormente para {symbol}. Ignorando nova entrada.")
            return

        market = exchange.market(symbol)
        min_qty = market['limits']['amount']['min']
        min_cost = market['limits'].get('cost', {}).get('min', 5.0)

        valor_total = qtd * preco

        if valor_total < min_cost:
            log(f"⚠ Valor da ordem {symbol} ({valor_total:.2f}) < mínimo permitido ({min_cost:.2f}). Ajustando para 5 USDT.")
            qtd = round(5 / preco, 6)

        if min_qty and qtd < min_qty:
            log(f"⚠ Qtd para {symbol} ({qtd}) < mínimo permitido ({min_qty}). Ajustando...")
            qtd = round(min_qty, 6)

        qtd = round(qtd, int(market['precision']['amount']))
        preco = round(preco, int(market['precision']['price']))

        if market.get("spot", False):
            params = {"category": "spot"}
        elif market.get("linear", False):
            params = {"category": "linear"}
        else:
            params = {"category": "linear"}

        order = exchange.create_limit_buy_order(symbol, qtd, preco, params)

        order_id = order.get('id', 'N/A')
        log(f"💰 COMPRA {symbol} | Qtd: {qtd} | Preço: {preco} | Ordem ID: {order_id}")
        registrar_trade_excel(symbol, 'buy', qtd, preco, ema50, ema200, atr, sl, tp)

        ordens_abertas_por_simbolo.add(symbol)

    except Exception:
        log(f"⚠ Erro ao executar ordem de compra para {symbol}:\n" + traceback.format_exc())

# ======================== ESTRATÉGIA PRINCIPAL ========================
def estrategia_scalping_com_backtest():
    log("🚀 Iniciando estratégia Scalping + Tendência + Backtest automático")
    while True:
        try:
            usdt = obter_saldo_usdt()
            if usdt < 10:
                log("⚠ Saldo insuficiente em USDT.")
                time.sleep(60)
                continue

            for symbol in symbols:
                if symbol in ordens_abertas_por_simbolo:
                    log(f"⚠ Já existe ordem aberta para {symbol}. Ignorando...")
                    continue

                if symbol not in exchange.markets:
                    log(f"⚠ Símbolo {symbol} não encontrado na exchange.")
                    continue

                ohlcv = obter_ohlcv(symbol, timeframe, 300)
                if not ohlcv:
                    continue

                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['EMA50'] = df['close'].ewm(span=50).mean()
                df['EMA200'] = df['close'].ewm(span=200).mean()
                closes = df['close'].tolist()
                preco_atual = closes[-1]
                ema50 = df['EMA50'].iloc[-1]
                ema200 = df['EMA200'].iloc[-1]
                atr = calcular_atr(ohlcv[-100:], period=14)

                log(f"📈 {symbol} | EMA50: {ema50:.2f} | EMA200: {ema200:.2f} | ATR: {atr if atr else 'N/A'}")

                if atr is None:
                    log(f"⚠ ATR não pôde ser calculado para {symbol}. Ignorando...")
                    continue

                if ema50 <= ema200:
                    log(f"⏸️ Tendência não favorável para {symbol} (EMA50 <= EMA200). Ignorando...")
                    continue

                trades_sim, acerto, lucro_sim = backtest_simples(df)
                log(f"📊 Backtest {symbol} | Trades: {trades_sim} | Acerto: {acerto:.1f}% | Lucro: {lucro_sim:.2f}%")

                if lucro_sim < 0:
                    log(f"⛔ Backtest ruim para {symbol}. Ignorando trade.")
                    continue

                tp_pct = 0.01
                sl_pct = 0.005
                tp = round(preco_atual * (1 + tp_pct), 2)
                sl = round(preco_atual * (1 - sl_pct), 2)
                qtd = round((usdt * risk_per_trade) / preco_atual, 6)

                log(f"🧠 Sinal confirmado para {symbol}. Executando compra...")
                executar_ordem_compra(symbol, qtd, preco_atual, ema50, ema200, atr, sl, tp)

            time.sleep(60)

        except Exception:
            log("🔥 Erro na estratégia:\n" + traceback.format_exc())
            time.sleep(60)

# ======================== EXECUÇÃO ========================
if __name__ == "__main__":
    sincronizar_tempo()
    verificar_ordens_abertas()
    estrategia_scalping_com_backtest()
