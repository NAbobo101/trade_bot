# 🤖 Bybit Scalping Trading Bot

Este projeto implementa um **bot de trading automatizado** para a exchange **Bybit**, utilizando uma estratégia de **scalping com confirmação de tendência** (EMA50 > EMA200) e **validação por backtest**.

O bot calcula indicadores técnicos (EMA, ATR), verifica ordens abertas, gerencia risco, registra operações em Excel e executa ordens de compra automaticamente com base nas condições de entrada.

## ✅ Funcionalidades

- 📈 Cálculo de indicadores técnicos (EMA50, EMA200, ATR)  
- 🧠 Backtest automatizado para validação do sinal  
- ⛔ Filtro por tendência (EMA50 > EMA200)  
- 🪙 Gestão de risco por percentual (ex: 5% do saldo)  
- 📊 Registro de trades em planilha `.xlsx`  
- 🧾 Log detalhado das decisões e ações em `.txt`  
- 🔐 Armazenamento seguro das credenciais via `credenciais.txt`  
- 🚫 Verificação de ordens abertas para evitar duplicidade  

## 📁 Estrutura do Projeto

```
trading-bot/
├── tradev1.py            # Código principal do bot
├── requirements.txt      # Lista de dependências
├── credenciais.txt       # (gerado na 1ª execução) Armazena API Key/Secret
├── trades_log.txt        # Log de execução (gerado automaticamente)
├── trades.xlsx           # Registro de operações (gerado automaticamente)
└── README.md             # Este arquivo
```

## 🚀 Como usar

### 1. Clone o repositório ou copie os arquivos

```
git clone https://github.com/NAbobo101/trade_bot.git
cd trade_bot
```

### 2. (Opcional) Crie e ative um ambiente virtual

```
python -m venv venv
source venv/bin/activate   # Linux/macOS
venv\Scripts\Activate  # Windows
```

### 3. Instale as dependências

```
pip install -r requirements.txt
```

### 4. Execute o bot

```
cd carteira_real
python tradev1.py
```

Na **primeira execução**, o bot pedirá que você informe a **API Key** e o **Secret** da sua conta Bybit. Esses dados serão salvos no arquivo `credenciais.txt` localmente para futuras execuções.

## 🔐 Como obter suas credenciais da Bybit

1. Acesse sua conta em: https://www.bybit.com  
2. Vá até seu perfil e clique em **"API"**  
3. Clique em **"Criar nova chave API"**  
4. Escolha **API de Sistema** ou **API de Subconta**  
5. Dê um nome e selecione permissões:  
   - Ative **Leitura de Dados**  
   - Ative **Negociação em Spot** (ou Derivativos se desejar)  
6. Copie a **API Key** e **Secret**  
7. Cole no terminal quando o bot solicitar  

💡 Recomenda-se usar uma **subconta ou chaves exclusivas para o bot**, com permissões restritas.

## 📦 Instalar dependências manualmente

Se precisar instalar sem `requirements.txt`, use:

```
pip install ccxt pandas numpy openpyxl
```

## ⚠️ Aviso de responsabilidade

> Este projeto é fornecido apenas para fins educacionais.  
> O uso com fundos reais envolve riscos financeiros.  
> Use por sua conta e risco.

## 👨‍💻 Autor

Desenvolvido por [NAbobo101](https://github.com/NAbobo101)
