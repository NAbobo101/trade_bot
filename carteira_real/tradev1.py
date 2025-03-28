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
posicoes_abertas = {}  # Novo dicionário para rastrear posições compradas

# ======================== LOG UTILITÁRIO ========================
def log(mensagem):
    agora = datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')
    log_msg = f"[{agora}] {mensagem}"
    print(log_msg)
    with open(log_file_path, "a", encoding="utf-8") as f:
        f.write(log_msg + "\n")

# ======================== GATILHO DE VENDA (GATILHO POR TENDÊNCIA DE QUEDA + LUCRO) ========================
def verificar_sinal_venda(symbol, df, preco_atual):
    if symbol not in posicoes_abertas:
        return False

    entrada = posicoes_abertas[symbol]['preco_entrada']
    lucro_minimo = entrada * 1.005  # lucro de pelo menos 0.5%

    ema50 = df['EMA50'].iloc[-1]
    ema200 = df['EMA200'].iloc[-1]

    if preco_atual > lucro_minimo and ema50 < ema200:
        return True

    return False

# ======================== VENDA ========================
def executar_ordem_venda(symbol, preco):
    try:
        base = symbol.split("/")[0]  # Ex: BTC em BTC/USDT
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

    except Exception as e:
        log(f"⚠ Erro na ordem de compra para {symbol}:\n{str(e)}")