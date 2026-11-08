import pandas as pd
import numpy as np


def calculate_features(df):
    df = df.copy()

    # Moving Averages
    df["SMA_20"] = df["Close"].rolling(20).mean()
    df["SMA_50"] = df["Close"].rolling(50).mean()
    df["EMA_20"] = df["Close"].ewm(span=20, adjust=False).mean()

    # RSI
    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["RSI"] = 100 - (100 / (1 + rs))

    # MACD
    ema_12 = df["Close"].ewm(span=12, adjust=False).mean()
    ema_26 = df["Close"].ewm(span=26, adjust=False).mean()

    df["MACD"] = ema_12 - ema_26
    df["MACD_SIGNAL"] = df["MACD"].ewm(span=9, adjust=False).mean()

    # Bollinger Bands
    sma_20 = df["Close"].rolling(20).mean()
    std_20 = df["Close"].rolling(20).std()

    df["BB_UPPER"] = sma_20 + (2 * std_20)
    df["BB_LOWER"] = sma_20 - (2 * std_20)

    # Volatility
    df["VOLATILITY"] = df["Close"].pct_change().rolling(20).std()

    # Momentum
    df["MOMENTUM"] = df["Close"].pct_change(10)

    return df