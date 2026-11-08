import MetaTrader5 as mt5

print("Connecting to MT5...")

if not mt5.initialize(
    path=r"C:\Program Files\MetaTrader 5\terminal64.exe",
    timeout=60000
):
    print("Connection Failed:", mt5.last_error())
else:
    print("MT5 Connected Successfully!")
    print("Version:", mt5.version())

    account = mt5.account_info()

    if account:
        print("Account:", account.login)
        print("Server:", account.server)
    else:
        print("Terminal connected, but no trading account is logged in.")

    mt5.shutdown()