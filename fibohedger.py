# External library imports (may require installation)
# For websockets
try:
    import websockets
except ImportError:
    print("Installing websockets library...")
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websockets"])
    import websockets
    print("Websockets library installed")

# For requests
try:
    import requests
except ImportError:
    print("Installing requests library...")
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests
    print("Requests library installed")

# For pycountry
try:
    import pycountry
except ImportError:
    print("Installing pycountry library...")
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pycountry"])
    import pycountry
    print("Pycountry library installed")

# For pynput
try:
    from pynput import keyboard
except ImportError:
    print("Installing pynput library...")
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pynput"])
    from pynput import keyboard
    print("Pynput library installed")

# Standard library imports (these do not require installation)
import json
import asyncio
import sys
import time
from datetime import datetime, timezone
import os
from difflib import get_close_matches
import csv
import urllib.parse
import hashlib
import hmac
import base64


# Global variables
connection_data = {
    "api_key": "",  # API key
    "private_key": "",  # API private key
    "ws_public": None,  # Public websocket connection
    "ws_private": None,  # Private websocket connection
    "ws_token": None,  # Websocket token
    "ws_rr": 0.1,  # Websocket receiver refresh rate
    "serverStatus": None,  # Server status: online, cancel_only, maintenance, post_only
    "startupFlag": True,  # To show connection status only on startup
    "closeFlag": True, # To close algorithm functions
    "terminalFlag": False, # To turno on/off terminal_printer()
    "ws_connection_handler_task" : None,  # Async task to handle websocket connections
    "rest_pnl_handler_task": None, # Time constrained functions async task
    "asyncio_close_event": None,  # Event to kill async coroutines at EOP
    "restAPIflag": True,  # Flag to indicate if REST API is active
    "eventsSubscriptionFlag": False,  # Events websocket subscription flag
    "tickerSubscriptionFlag": False,  # Ticker websocket subscription flag
    "spot_balances": [], # Spot available balances to select quote currency
    "errorLog": [] # # Errors to print on screen
}

asset_data = {
    "altname": None,  # Commercial asset name
    "wsname": None,  # Asset code (/)
    "base": None,  # Base currency
    "quote": { # Quote currency
        "asset": None, # Quote code
        "altname": None, # Quote name
        "decimals": 0, # Quote decimals
        "amount": 0.0 # Quote amount
        },
    "ask": 0,  # Ask price
    "bid": 0,  # Bid price
    "leverage": 0, # Selected leverage
    "cost_decimals": 0, # Cost decimals
    "pair_decimals": 0, # Pair decimals
    "lot_decimals": 0, # Lot decimals
    }

algo_data = {
    "initialBalance": 0, # Balance at beginning of batch of trades
    "balance": 0, # Current balance
    "margin": 0, # Current margin
    "positionSize%": 6.1803, # Position size as % of balance
    "positionValue": 0, # Position value as quote currency
    "positionSize": 0, # Position size as base currency
    "step": 0, # Current step
    "bought": False, # Flag to indicate if position is bought
    "limbo%": 0.1, # The distant between entry points as % of price
    "tpIncrement": 1.61803, # TP increment as % of price
    "tp%": 1.61803, # TP as % of price
    "refPrice": 0, # Reference price (middle price in limbo)
    "longPrice": 0, # Long entry price
    "shortPrice": 0, # Short entry price
    "longTP": 0, # Long TP price
    "shortTP": 0, # Short TP price
    "type": None, # Type of trade (long/short)
    "pendingOrders": [],  # List of pending orders {"pair", "step", "type", "id", "status"}
    "openPositions": [],  # List of open positions {"pair", "type", "ordertype", "volume", "step", "id", "pnl"}
    "pastPositionsBuffer": [],  # Buffer to store past positions {"pair", "type", "ordertype", "volume", "step", "id", "pnl"}
    "lastBatch": {"ts": 0, "pair": None, "initialBalance": 0, "endBalance": 0, "pnl": 0, "pnl%": 0, "step": 0, "type": "batch"} # Pnl from last batch of trades
    }

### Main function
async def main():
    global connection_data, asset_data, algo_data

    # Print logo
    print_logo() 

    # Create log files
    log_to_csv(algo_data["lastBatch"], "tradesLog.csv", True)
    log_to_csv({"ts": 0, "error": ""}, "errorLog.csv", True)
    
    # Create asyncio close event
    connection_data["asyncio_close_event"] = asyncio.Event()
    
    # Initialize websockets receiver
    await websockets_init()

    # Initialize connection
    if connection_data["closeFlag"] == True:
        await connection_init()

    # User available quote currency retrieval and input
    if connection_data["closeFlag"] == True:
        await input_quote_currency()

    # User input for leverage
    if connection_data["closeFlag"] == True:
        await input_leverage()

    # User input for country code
    if connection_data["closeFlag"] == True:
        country_code = await input_country_code()

    # Retrieve asset pairs
    if connection_data["closeFlag"] == True:
        asset_pairs = get_asset_pairs(country_code)

    # User input for base currency
    if connection_data["closeFlag"] == True:
        input_base_currency(asset_pairs)

    # Recap and start algorithm
    if connection_data["closeFlag"] == True:
        input_recap()

    # Websockets subscriptions
    if connection_data["closeFlag"] == True:
        await ws_subscriptions()

    # Hotkeys initialization
    if connection_data["closeFlag"] == True:
        hotkeys = keyboard.GlobalHotKeys({
            "<ctrl>+<shift>+q": kill_and_close,
            "<ctrl>+<shift>+c": clear_errors
            })
    
        hotkeys.start()

    # Algorithm loop
    while connection_data["closeFlag"]:
        await algo_reset()
        await algo_stepper()
        
        await asyncio.sleep(1)

    # Turn off terminal printer
    connection_data["terminalFlag"] = False

    print("\n------------------------------------------------------------------------------------------\n")
    print(local_time(), "Cancelling pending orders...")
    
    # Cancel pending orders
    while True:
        rest_cancel_all()
        await asyncio.sleep(2)
        if len(algo_data["pendingOrders"]) == 0:
            print(local_time(), "Pending orders cancelled.")
            break

    print(local_time(), "Closing open positions...")

    # Close open positions
    for position in algo_data["openPositions"]:
        await rest_close_position(position)

    while True:
        if len(algo_data["openPositions"]) == 0:
            print(local_time(), "Open positions closed.")
            break
        await asyncio.sleep(1)

    # Close all coroutines
    connection_data["asyncio_close_event"].set()

    # Close async tasks
    connection_data["ws_connection_handler_task"].cancel() 
    connection_data["rest_pnl_handler_task"].cancel()

    # End program
    sys.exit(f"\n{local_time()} EOP")

#################################### USER MENU FUNCTIONS ################################################


### Print logo
def print_logo():
    clear_terminal()

    # Open and print logo file
    logo_path = os.path.join(os.path.dirname(__file__), "logo")

    try:
        with open(logo_path, "r") as logo_file:
            print(logo_file.read())
    except:
        print("Logo missing!\n")

    return


### Clear terminal
def clear_terminal():
    # For Windows
    if os.name == 'nt':
        os.system('cls')
    # For macOS and Linux (here, os.name is 'posix')
    else:
        os.system('clear')


### Clear errors log
def clear_errors():
    global connection_data

    connection_data["errorLog"] = []


### User input for API credentials
def credentials_input(reset_credentials = False):
    global connection_data

    # Define folder and file paths
    folder_path = os.path.join(os.path.dirname(__file__), "login_credentials")

    # Check if the folder exists, and create it if it doesn't
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)

    api_key_path = os.path.join(folder_path, "apikey.txt")
    private_key_path = os.path.join(folder_path, "private_key.txt")

    # Create files if they don't exist
    if not os.path.exists(api_key_path):
        with open(api_key_path, "w") as api_key_file:
            api_key_file.write("")

    if not os.path.exists(private_key_path):
        with open(private_key_path, "w") as private_key_file:
            private_key_file.write("")


    # Reset credentials if wrong
    if reset_credentials == True:
        connection_data["api_key"] = ""
        connection_data["private_key"] = ""

        with open(api_key_path, "w") as api_key_file:
            api_key_file.write("")
        with open(private_key_path, "w") as private_key_file:
            private_key_file.write("")

    # Read credentials from file
    with open(api_key_path, "r") as api_key_file:
        connection_data["api_key"] = api_key_file.read().strip()

    with open(private_key_path, "r") as private_key_file:
        connection_data["private_key"] = private_key_file.read().strip()

    # Ask for credentials if empty
    if connection_data["api_key"] == "" or connection_data["private_key"] == "":
        print("\nPlease enter your Kraken API credentials.")
        connection_data["api_key"] = input("API Key: ").strip()
        connection_data["private_key"] = input("Private Key: ").strip()

        # Write credentials to file
        with open(api_key_path, "w") as api_key_file:
            api_key_file.write(connection_data["api_key"])

        with open(private_key_path, "w") as private_key_file:
            private_key_file.write(connection_data["private_key"])


### Select country code
async def input_country_code():

    clear_terminal()

    # List of country codes
    country_list = [country.alpha_2 for country in pycountry.countries]
    
    # Country code input
    while not connection_data["asyncio_close_event"].is_set():
        await asyncio.sleep(1)

        country_code = input("\nEnter a country code to filer tradable assets\n(type 'list' to list all, leave empty for no coutry filter): ")

        match country_code:
            case "list":
                for country in country_list:
                    print(f"Code: {country} - Country: {pycountry.countries.get(alpha_2=country).name}")
                print("\n")
                continue
            case "":
                print("No country filter selected.")
                country_code = None
                break

        country_code = country_code.upper()
        
        if country_code in country_list:
            country_name = pycountry.countries.get(alpha_2=country_code).name
            print("Country selected: ", country_name)
            break
        else:
            print("Invalid country code. Please try again.")
    
    # Regional subcode input
    if country_code:
        subcode_list = pycountry.subdivisions.get(country_code=country_code)
        subcode_list = [subd.code.split('-')[1] for subd in subcode_list]

        while not connection_data["asyncio_close_event"].is_set():
            subcode = input("\nEnter a regional subcode to filer tradable assets\n(type 'list' to list all, leave empty for no regional subcode filter): ")
            
            match subcode:
                case "list":
                    for sub in subcode_list:
                        print(f"Code: {sub} - Area: {pycountry.subdivisions.get(code=f'{country_code}-{sub}').name}")
                    print("\n\n")
                    continue
                case "":
                    print("No regional subcode filter selected.")
                    subcode = None
                    break

            subcode = subcode.upper()
            
            if subcode in subcode_list:
                subcode_name = pycountry.subdivisions.get(code=f'{country_code}-{subcode}').name
                print("Regional subcode selected: ", subcode_name)
                country_code = f"{country_code}:{subcode}"
                break
            else:
                print("Invalid regional subcode. Please try again.")

    await asyncio.sleep(1)

    # Print and return selected country code
    if country_code:
        location_buffer = f"Selected country: {country_code} - {country_name}"

        if subcode:
            location_buffer += f", {subcode_name}"

        print(location_buffer, "\n\n")
    else:
        print("No country code selected\n\n")

    return country_code


### Select leverage
async def input_leverage():
    global asset_data

    clear_terminal()

    # Leverage input
    while not connection_data["asyncio_close_event"].is_set():
        await asyncio.sleep(1)
        leverage = input("\nEnter a leverage to filter tradable assets (1-5): ")

        try:
            leverage = int(leverage)
            if leverage in range(1, 6):
                asset_data["leverage"] = leverage
                print("Leverage selected: ", asset_data["leverage"])
                break
            else:
                print("Invalid value, please enter a numeric value.")
        except:
            print("Invalid leverage, please enter a value between 1 and 5.")
    
    await asyncio.sleep(1)
    

### Select quote currency
async def input_quote_currency():
    global connection_data, asset_data
    currenciesBuffer = []

    # Request available currencies
    url = "https://api.kraken.com/0/public/Assets"

    payload = {}
    headers = {
    'Accept': 'application/json'
    }

    response = requests.request("GET", url, headers=headers, data=payload).json()

    # Handle errors
    if len(response["error"]) == 0:
        response = response["result"]
    else:
        print(local_time(), response["error"])
        kill_and_close()
        return

    # Retrieve available quote currencies
    for asset_key in response:
        asset_info = response[asset_key]
        for currency in connection_data["spot_balances"]:
            if currency["asset"] == asset_info["altname"]:
                currencyBuffer = {
                    "asset": asset_key,
                    "altname": asset_info["altname"],
                    "decimals": int(asset_info["decimals"]),
                    "amount": float(currency["amount"])
                }
                currenciesBuffer.append(currencyBuffer)

    # Select quote currency
    while not connection_data["asyncio_close_event"].is_set():
        await asyncio.sleep(1)
        print("\nAvailable currencies:")

        for i in range(0, len(currenciesBuffer)):
            print(f"{i+1} - {currenciesBuffer[i]['altname']} - Amount: {currenciesBuffer[i]['amount']:.{currenciesBuffer[i]['decimals']}f}")

        user_input = input(f"\nSelect a quote currency [1, {len(currenciesBuffer)}]: ")

        try:
            user_input = int(user_input)
        except:
            print("Invalid input, please enter a valid integer.")
            continue

        if user_input in range(1, len(currenciesBuffer)+1):
            asset_data["quote"] = currenciesBuffer[user_input-1]
            connection_data["spot_balances"] = currenciesBuffer[user_input-1]
            print(f"Quote currency selected: {asset_data["quote"]["altname"]}")
            break
        else:
            print("Selection out of range, please try again.")
    
    await asyncio.sleep(1)


### Select asset pairs
def get_asset_pairs(country_code):
    global asset_data

    # Request asset pairs
    url = "https://api.kraken.com/0/public/AssetPairs"
    
    params = {}
    if country_code:
        params["country_code"] = country_code
    
    headers = {
        'Accept': 'application/json'
    }
    
    response = requests.get(url, headers=headers, params=params)
    
    # Filter asset pairs based on selected leverage and quote currency
    if response.status_code == 200:
        assets = response.json().get("result", {})
        asset_info_list = []
        for asset, info in assets.items():
            if asset_data["leverage"] != 1:
                leverage_buy = info.get("leverage_buy", [])
                leverage_sell = info.get("leverage_sell", [])
                if asset_data["leverage"] not in leverage_buy or asset_data["leverage"] not in leverage_sell:
                    continue
            if asset_data["quote"]["asset"] != info.get("quote"):
                continue
            asset_info = {
                "altname": info.get("altname"),
                "wsname": info.get("wsname"),
                "base": info.get("wsname").split("/")[0],
                "quote": info.get("quote"),
                "status": info.get("status"),
                "cost_decimals": info.get("cost_decimals"),
                "pair_decimals": info.get("pair_decimals"),
                "lot_decimals": info.get("lot_decimals"),
                "lot_multiplier": info.get("lot_multiplier"),
                "leverage_buy": info.get("leverage_buy"),
                "leverage_sell": info.get("leverage_sell"),
                "fees": info.get("fees"),
                "fees_maker": info.get("fees_maker"),
                "ordermin": info.get("ordermin"),
                "costmin": info.get("costmin")
            }
            asset_info_list.append(asset_info)
    else:
        # Handle errors
        error = response.json().get("error", [])
        print(local_time(), "Error:\n", local_time(True), error)
        kill_and_close()
        return
    
    return asset_info_list


### Select base asset
def input_base_currency(asset_info_list):
    global asset_data
    asset_buffer = None

    clear_terminal()

    # For less than 10 assets, build a menu and select an asset by entering the menu index 
    if len(asset_info_list) < 10:
        while not connection_data["asyncio_close_event"].is_set():
            print("Available assets:")
            for i in range(0, len(asset_info_list)):
                print(f"{i+1} - {asset_info_list[i]['base']}")
            try:
                user_input = int(input(f"\nSelect a base asset [1, {len(asset_info_list)}]: "))
            except:
                clear_terminal()
                print("\nInvalid input, please enter a valid integer.\n\n")
                continue
            if user_input not in range(1, len(asset_info_list)+1):
                clear_terminal()
                print("\nSelection out of range, please try again.\n\n")
                continue
            asset_buffer = asset_info_list[user_input-1]
            break
    # For 10 assets or more, search or list assets and select asset by entering assetvname
    else:
        asset_buffer = [asset["base"] for asset in asset_info_list]

        while not connection_data["asyncio_close_event"].is_set():
            user_input = input(f"\nSearch base asset ({len(asset_buffer)} assets found)\n('list all' to list all assets)\nSearch: ").upper().strip()
            if user_input == "LIST ALL":
                clear_terminal()
                print("\nAvailable assets:")
                for asset in asset_buffer:
                    print(asset)
                continue

            elif user_input in asset_buffer:
                for row in asset_info_list:
                    if row["base"] == user_input:
                        print(row)
                        asset_buffer = row
                        break
                print(f"Base asset selected: {user_input}")
                break

            else:
                matches = get_close_matches(user_input, asset_buffer, 80)
                if len(matches) > 0:
                    clear_terminal()
                    print(f"\n{user_input}: invalid asset, did you mean:\n")
                    for match in matches:
                        print(match)
                else:
                    clear_terminal()
                    print(f"\n{user_input}: invalid asset, please try again.")

    # Save asset specs in asset_data
    try:
        asset_data["altname"] = asset_buffer["altname"]
        asset_data["wsname"] = asset_buffer["wsname"]
        asset_data["base"] = asset_buffer["base"]
        asset_data["cost_decimals"] = int(asset_buffer["cost_decimals"])
        asset_data["pair_decimals"] = int(asset_buffer["pair_decimals"])
        asset_data["lot_decimals"] = int(asset_buffer["lot_decimals"])
    except e:
        print(f"Internal error on asset selection:\n{e}")
        kill_and_close()
        return

    clear_terminal()


### Recap and start algorithm
def input_recap():
    global asset_data, connection_data

    clear_terminal()

    print("RECAP:\n",
        f"  Symbol: {asset_data['wsname']}\n",
        f"  Leverage: {asset_data['leverage']}\n",
        f"  Budget: {asset_data['quote']['amount']} {asset_data['quote']['altname']}\n",
        f"  Leveraged margin: {asset_data['quote']['amount'] * asset_data['leverage']} {asset_data['quote']['altname']}\n"
        )

    while True:
        user_input = input("Do you want to proceed? (y/n): ").upper()

        match user_input:
            case "Y":
                break
            case "N":
                kill_and_close()
                return
            case _:
                print("Invalid input, please try again.\n")

    print("\n\n")

#################################### SYSTEM FUNCTIONS ################################################

### Returns local time (string)
def local_time(only_space = False):
    timeBuffer = str(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    match only_space:
        case False:
            return timeBuffer + " -"
        case True:
            return (" " * len(timeBuffer)) + " ---"

### Returns local machine time in millisenconds
# Str: nonce for REST private requests
# Int: timestamp for csv logs
def get_timestamp(integer = False):
    ts = int(time.time() * 1000)

    if integer == False:
        return str(ts)
    
    return ts

### Executes functions every second, minute or hour
async def rest_pnl_handler():

    while not connection_data["asyncio_close_event"].is_set():
        if connection_data["restAPIflag"] == True:
            rest_pnl_request()
        await asyncio.sleep(3)

### Kills tasks and closes program
def kill_and_close():
    global connection_data

    print("Closing program...")
    
    connection_data["closeFlag"] = False

### Log into CSV
def log_to_csv(data, filename, overwrite=False):
    # Find the current directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    log_directory = os.path.join(script_dir, "log")
    
    # Ensure the 'log' directory exists
    os.makedirs(log_directory, exist_ok=True)
    
    # Construct the full file path
    full_path = os.path.join(log_directory, filename)
    
    if overwrite:
        # Create or overwrite file: open in write mode, write header and row
        with open(full_path, mode='w', newline='') as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=data.keys())
            writer.writeheader()
        return

    # Check if file exists
    file_exists = os.path.isfile(full_path)
    
    with open(full_path, mode='a', newline='') as csv_file:
        # Create a DictWriter using the keys of the dictionary as fieldnames
        writer = csv.DictWriter(csv_file, fieldnames=data.keys())
        
        # Write header if file does not exist or is empty
        if not file_exists or os.stat(full_path).st_size == 0:
            writer.writeheader()
        
        # Write the row from the dictionary
        writer.writerow(data)


################################## CONNECTION FUNCTIONS #################################

### Websockets connection initialization
async def websockets_init():
    global connection_data

    print(local_time(), "Connecting...")

    # Initialize websocket connection
    counter = 0
    while not connection_data["asyncio_close_event"].is_set():
        try:
            connection_data["ws_private"] = await websockets.connect("wss://ws-auth.kraken.com/v2")
            connection_data["ws_public"] = await websockets.connect("wss://ws.kraken.com/v2")
        except Exception as e:
            counter += 1
            if counter > 5:
                print(local_time(), "Unable to connect, closing program.")
                kill_and_close()
                return
            print(local_time(), f"Connection error, trying again ({counter}):")
            print(local_time(True), e)
            await asyncio.sleep(counter)
            continue
        break

    # Start websocket connection handler task
    if connection_data["startupFlag"] == True:
        connection_data["ws_connection_handler_task"] = asyncio.create_task(ws_connection_handler())

    # Wait for websocket connection to be established
    while not connection_data["asyncio_close_event"].is_set():
        await asyncio.sleep(1)

        match connection_data["serverStatus"]:
            case None:
                continue
            case "online":
                print(local_time(), "Server status: OK")
                break
            case _:
                print(local_time(), "Server unavailable:")
                print(local_time(True), f"Server status: {connection_data["serverStatus"]}")
                kill_and_close()
                return


### Rest connection initialization
async def connection_init():
    global connection_data

    # Get API credentials
    credentials_input()

    # Get websocket token
    while get_ws_token() == False:
        await asyncio.sleep(1)
        print("\nInvalid credentials, please try again")
        credentials_input(True)

    # Balances websocket subscription
    await subscribe_balances()
    
    # Wait for balances to be available
    while len(connection_data["spot_balances"]) == 0:
        await asyncio.sleep(1)
    
    # Create task to update PnL
    connection_data["rest_pnl_handler_task"] = asyncio.create_task(rest_pnl_handler())  

    clear_terminal()  


### Websockets subscriptions
async def ws_subscriptions():
    global asset_data, connection_data

    print("Waiting for websockets subscriptions...\n")

    # Subscribe to orders executions
    await subscribe_executions()

    await asyncio.sleep(1)

    # Subscribe to asset ticker
    await subscribe_ticker(asset_data["wsname"])

    while not connection_data["eventsSubscriptionFlag"] or not connection_data["tickerSubscriptionFlag"]:
        await asyncio.sleep(2)
    
    clear_terminal()


### Returns REST signature
def rest_signature(urlpath, data):
    global connection_data

    # Create signature (check Kraken API page for details)
    if isinstance(data, str):
        encoded = (str(json.loads(data)["nonce"]) + data).encode()
    else:
        encoded = (str(data["nonce"]) + urllib.parse.urlencode(data)).encode()
    message = urlpath.encode() + hashlib.sha256(encoded).digest()
    mac = hmac.new(base64.b64decode(connection_data["private_key"]), message, hashlib.sha512)
    sigdigest = base64.b64encode(mac.digest())
    return sigdigest.decode()


### Gets websocket token
def get_ws_token():
    global connection_data

    # REST request
    url = "https://api.kraken.com/0/private/GetWebSocketsToken"

    payload = json.dumps({
    "nonce": get_timestamp()
    })

    try:
        headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'API-Key': connection_data["api_key"],
        'API-Sign': rest_signature('/0/private/GetWebSocketsToken', payload)
        }
    except:
        return False
    response = requests.request("POST", url, headers=headers, data=payload).json()

    # Check response
    if not response.get("error") and response.get("result"):
        connection_data["ws_token"] = str(response["result"]["token"])
        if connection_data["startupFlag"] == True:
            print(local_time(), "REST credentials: OK")
            print(local_time(), "Private WebSocket token: OK")
            return True
    # Handle errors
    else:
        connection_data["errorLog"].append({"ts": get_timestamp(True), "error": response["error"]})
        log_to_csv(connection_data["errorLog"][-1], "errorLog.csv")
        connection_data["ws_token"] = None
        connection_data["api_key"] = ""
        connection_data["private_key"] = ""
        if response["error"][0] != "EAPI:Invalid key":
            print(local_time(), "ERROR:")
            print(local_time(True), response["error"][0])
        return False

################################# INCOMING WEBSOCKET HANDLING ###################################

### Websocket response handler (public and private)
async def ws_connection_handler():
    global connection_data

    # Constantly checks on websocket connections
    while not connection_data["asyncio_close_event"].is_set():
        # Checks on private websocket
        try:
            response = await asyncio.wait_for(connection_data["ws_private"].recv(), timeout=connection_data["ws_rr"])
            response = json.loads(response)
            ws_message_parser(response, ws_type = "Private")
        except:
            ...
        # Checks on public websocket
        try:
            response = await asyncio.wait_for(connection_data["ws_public"].recv(), timeout=connection_data["ws_rr"])
            response = json.loads(response)
            ws_message_parser(response)
        except:
            ...
        # Prints on terminal if terminalFlag is True
        if connection_data["terminalFlag"]:
            terminal_printer()
            
    
### Websocket response parser (public and private)
def ws_message_parser(response, ws_type = "Public"):
    global connection_data, asset_data, algo_data


    # Initial connection response
    if response.get("channel") == "status" and response.get("data") and isinstance(response["data"], list) and response["data"][0].get("system"):
        connection_data["serverStatus"] = response["data"][0]["system"]
        match connection_data["serverStatus"]:
            case "online":
                if connection_data["startupFlag"] == True:
                    print(local_time(), f"{ws_type} WebSocket connection status: {connection_data["serverStatus"]}")
            case "cancel_only":
                print(local_time(), f"{ws_type}WebSocket connection status: {connection_data["serverStatus"]}") # TODO
            case "maintenance":
                print(local_time(), f"{ws_type}WebSocket connection status: {connection_data["serverStatus"]}") # TODO
            case "post_only":
                print(local_time(), f"{ws_type}WebSocket connection status: {connection_data["serverStatus"]}") # TODO

    # Ping response
    elif response.get("method") == "pong":
        return

    # Subscriptions heartbeat
    elif response.get("channel") == "heartbeat":
        return

    # Ticker subscription ok
    elif response.get("method") == "subscribe" and response.get("result") and response["result"].get("channel") == "ticker":
        if connection_data["startupFlag"] == True:
            print(local_time(), f"{response["result"].get("symbol")} ticker subscription: OK")
            connection_data["tickerSubscriptionFlag"] = True

    # Ticker subscription data
    elif response.get("channel") == "ticker" and response.get("data") and isinstance(response["data"], list) and response["data"][0].get("symbol"):
        response = response["data"][0]
        asset_data["ask"] = float(response["ask"])
        asset_data["bid"] = float(response["bid"])
            
    # Executions subscription ok
    elif response.get("method") == "subscribe" and response.get("result") and response["result"].get("channel") == "executions" and response.get("success") == True:
        if connection_data["startupFlag"] == True:
            print(local_time(), "Executions subscription: OK")
            connection_data["eventsSubscriptionFlag"] = True

    # Executions subscription data (SNAPSHOT) (UNUSED)
    elif response.get("channel") == "executions" and response.get("type") == "snapshot":
        return

    # Executions subscription data (UPDATE)
    elif response.get("channel") == "executions" and response.get("type") == "update":
        for execution in response["data"]:
            executions_handler(execution)

    # Balances subscription OK
    elif response.get("method") == "subscribe" and response.get("result") and response["result"].get("channel") == "balances" and response.get("success") == True:
        if connection_data["startupFlag"] == True:
            print(local_time(), "Balances subscription: OK")

    # Balances subscription NO BALANCE
    elif response.get("channel") == "balances" and response.get("type") == "snapshot" and len(response["data"]) == 0:
        print(local_time(), "No spot balances available\nPlease move the desired currency assets into the spot wallet")
        kill_and_close()
        return

    # Balances subscription data
    elif response.get("channel") == "balances" and len(response["data"]) > 0:
        # Snapshot
        if response.get("type") == "snapshot":
            print(local_time(), "BALANCES SNAPSHOT:")
            for asset_buffer in response["data"]:
                if asset_buffer["asset_class"] == "currency":
                    for wallet in asset_buffer["wallets"]:
                        try:
                            wallet["balance"] = float(wallet["balance"])
                        except:
                            continue
                        connection_data["spot_balances"].append({"asset": asset_buffer["asset"], "wallet": wallet["type"], "amount": wallet["balance"]})
                        print(local_time(True), f"Currency: {connection_data['spot_balances'][-1]['asset']} - Amount: {connection_data['spot_balances'][-1]['amount']:.8f}")
        # Update
        if response.get("type") == "update":
            for asset in response["data"]:
                if asset["asset"] == asset_data["quote"]["altname"] and asset["wallet_type"] == "spot":
                    asset_data["quote"]["amount"] = float(asset["balance"])
    
    # Non-parsed data packets
    else:
        # Handle unexpected errors
        if (response["error"] and len(response["error"]) > 0):
            for error in response["error"]:
                connection_data["errorLog"].append({"ts": get_timestamp(True), "error": error})
                log_to_csv(connection_data["errorLog"][-1], "errorLog.csv")
                if connection_data["terminalFlag"] == False:
                    print(local_time(), "ERROR:", error)            

# Handles executions from subscription
def executions_handler(execution):
    global asset_data, algo_data

    # Check execution type    
    match execution['exec_type']:
        case "pending_new":
            foundFlag = False
            # Check for duplicates in pendingOrders 
            for order in algo_data["pendingOrders"]:
                if order["id"] == execution["order_id"]:
                    foundFlag = True
            # Add to pendingOrders if not found
            if not foundFlag:
                algo_data["pendingOrders"].append({
                    "pair": asset_data["altname"],
                    "initialBalance": algo_data["balance"],
                    "type": execution["side"],
                    "step": int(execution["order_userref"]),
                    "id": execution["order_id"],
                    "status": "pending"})
        case "new":
            # set order status as accepted
            for order in algo_data["pendingOrders"]:
                if order["id"] == execution["order_id"]:
                    order["status"] = "ok"
        case "filled":
            orderBuffer = None
            positionBuffer = None

            # Find and remove order in pendingOrders
            for order in algo_data["pendingOrders"]:
                if order["id"] == execution["order_id"]:
                    orderBuffer = order
                    algo_data["pendingOrders"] = [o for o in algo_data["pendingOrders"] if o["id"] != execution["order_id"]]
            # Create position from order
            if orderBuffer != None:
                positionBuffer = {
                    "pair": orderBuffer["pair"],
                    "type": orderBuffer["type"],
                    "initialBalance": orderBuffer["initialBalance"],
                    "volume": float(execution["cum_qty"]),
                    "step": int(execution["order_userref"]),
                    "id": execution["order_id"],
                    "pnl": 0}

            foundFlag = False
            for position in algo_data["openPositions"]:
                # Check for duplicates in openPositions
                if position["id"] == positionBuffer["id"]:
                    foundFlag = True
                # Handle closing positions
                if position["pair"] == positionBuffer["pair"] and position["volume"] == positionBuffer["volume"] and position["type"] != positionBuffer["type"]:
                    closed_position_handler(position["id"])
                    foundFlag = True

            # Add to openPositions if not found
            if not foundFlag and positionBuffer != None:
                algo_data["openPositions"].append(positionBuffer)

        case "canceled":
            # Remove from pendingOrders
            algo_data["pendingOrders"] = [o for o in algo_data["pendingOrders"] if o["id"] != execution["order_id"]]
            closed_position_handler(execution["order_id"])

        case "expired":
            # Remove from pendingOrders
            algo_data["pendingOrders"] = [o for o in algo_data["pendingOrders"] if o["id"] != execution["order_id"]]
            closed_position_handler(execution["order_id"])

        case _:
            return

################################## WEBSOCKET REQUESTS #####################################################

### Websocket ticker subscription (public)
async def subscribe_ticker(symbol):
    global connection_data

    # REST request
    message = {
        "method": "subscribe",
        "params": {
            "channel": "ticker",
            "symbol": [symbol]
        }
    }
    await connection_data["ws_public"].send(json.dumps(message))


### Websocket executions subscription (private)
async def subscribe_executions():
    global connection_data

    # REST request
    message = {
        "method": "subscribe",
        "params": {
            "channel": "executions",
            "token": connection_data["ws_token"],
            "snap_orders": False,
            "snap_trades": False,
            "ratecounter": True
        }
    }

    await connection_data["ws_private"].send(json.dumps(message))


### Websocket balances subscription (pivate)
async def subscribe_balances():
    global connection_data

    # REST request
    message = {
        "method": "subscribe",
        "params": {
            "channel": "balances",
            "snapshot": True,
            "token": connection_data["ws_token"],
        }
    }
    await connection_data["ws_private"].send(json.dumps(message))


###################################### REST ORDER REQUESTS ############################################


### Long and short STOP order (with SL)
def rest_open_order(pair, volume, price, type, orderType, uref = 0):
    global connection_data, algo_data, asset_data

    # REST request
    url = "https://api.kraken.com/0/private/AddOrder"

    payload = json.dumps({
        "nonce": get_timestamp(),
        "ordertype": orderType,
        "type": type,
        "pair": pair,
        "volume": str(volume),
        "price": str(price),
        "userref": uref,
        "leverage": str(asset_data["leverage"])
        })

    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'API-Key': connection_data["api_key"],
        'API-Sign': rest_signature('/0/private/AddOrder', payload)
        }

    connection_data["restAPIflag"] = False
    response = requests.request("POST", url, headers=headers, data=payload).json()
    connection_data["restAPIflag"] = True

    # Handle errors
    if len(response["error"]) > 0:
        for error in response["error"]:
            connection_data["errorLog"].append({"ts": get_timestamp(True), "error": error})
            log_to_csv(connection_data["errorLog"][-1], "errorLog.csv")
            if connection_data["terminalFlag"] == False:
                print(local_time(), "ERROR:", error)
        return

    # Handle successful order and add to pendingOrders
    if len(response["error"]) == 0 and response["result"] and response["result"]["txid"] and len(response["result"]["txid"]) > 0:
        position = {
            "pair": pair,
            "initialBalance": algo_data["balance"],
            "step": uref,
            "type": type,
            "id": response["result"]["txid"][0],
            "status": "pending"
        }

        algo_data["pendingOrders"].append(position)
        return position["id"]


### Long and short CLOSE position
async def rest_close_position(position, price = 0):
    global connection_data, algo_data, asset_data

    # Define order type
    if price == 0:
        ordertype = "market"
    else:
        ordertype = "limit"

    # Find opposite direction
    type = "buy"
    if position["type"] == "buy":
        type = "sell"

    # REST request
    url = "https://api.kraken.com/0/private/AddOrder"

    payload = json.dumps({
        "nonce": get_timestamp(),
        "ordertype": ordertype,
        "type": type,
        "volume": "0",
        "pair": position["pair"],
        "price": str(price),
        "leverage": asset_data["leverage"]
        })

    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'API-Key': connection_data["api_key"],
        'API-Sign': rest_signature('/0/private/AddOrder', payload)
        }

    connection_data["restAPIflag"] = False

    response = requests.request("POST", url, headers=headers, data=payload).json()

    connection_data["restAPIflag"] = True

    # Handle errors
    if len(response["error"]) > 0:
        for error in response["error"]:
            connection_data["errorLog"].append({"ts": get_timestamp(True), "error": error})
            log_to_csv(connection_data["errorLog"][-1], "errorLog.csv")
            if connection_data["terminalFlag"] == False:
                print(local_time(), "ERROR:", error)
        rest_close_position(position, price)
        return

    # Handle successful order and add to pendingOrders
    if len(response["error"]) == 0 and response["result"] and response["result"]["txid"] and len(response["result"]["txid"]) > 0:
        algo_data["pendingOrders"].append({
            "pair": position["pair"],
            "initialBalance": algo_data["balance"],
            "step": position["step"],
            "type": type,
            "id": response["result"]["txid"][0],
            "status": "pending"
        })


### Cancels all pending orders
def rest_cancel_all():
    global connection_data

    # REST request
    url = "https://api.kraken.com/0/private/CancelAll"

    payload = json.dumps({
        "nonce": get_timestamp(),
        })

    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'API-Key': connection_data["api_key"],
        'API-Sign': rest_signature('/0/private/CancelAll', payload)
        }

    connection_data["restAPIflag"] = False

    response = requests.request("POST", url, headers=headers, data=payload).json()

    connection_data["restAPIflag"] = True

    # Handle errors
    if len(response["error"]) > 0:
        for error in response["error"]:
            connection_data["errorLog"].append({"ts": get_timestamp(True), "error": error})
            log_to_csv(connection_data["errorLog"][-1], "errorLog.csv")
            if connection_data["terminalFlag"] == False:
                print(local_time(), "ERROR:", error)
        return


### Gets PnL for open positions
def rest_pnl_request():
    global connection_data, algo_data

    # REST request
    url = "https://api.kraken.com/0/private/OpenPositions"

    payload = json.dumps({
        "nonce": get_timestamp(),
        "docalcs": True
        })

    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'API-Key': connection_data["api_key"],
        'API-Sign': rest_signature('/0/private/OpenPositions', payload)
        }

    response = requests.request("POST", url, headers=headers, data=payload).json()

    # Handle errors
    if len(response["error"]) > 0:
        for error in response["error"]:
            connection_data["errorLog"].append({"ts": get_timestamp(True), "error": error})
            log_to_csv(connection_data["errorLog"][-1], "errorLog.csv")
            if connection_data["terminalFlag"] == False:
                print(local_time(), "ERROR:", error)
        return

    # Handle successful response
    if response["result"]:
        # If no positions open
        if len(response["result"]) == 0:
            closed_position_handler(0)
        else:
            # build a list of orders and positions ids
            id_buffer = list(response["result"].keys())
            response_ids = []

            for id in id_buffer:
                response_ids.append({"position": id, "order": response["result"][id]["ordertxid"]})

            # check if positions in memory still exist and update pnl
            for position in algo_data["openPositions"]:
                foundFlag = False
                for id in response_ids:
                    if position["id"] == id["order"]:
                        position["pnl"] = float(response["result"][id["position"]]["net"])
                        foundFlag = True
                # If position doesn't exist anymore
                if foundFlag == False:
                    closed_position_handler(position["id"])

# Handles closed positions
def closed_position_handler(position_id):
    global algo_data

    # Remove all positions
    if position_id == 0:
        for position in algo_data["openPositions"]:
            algo_data["pastPositionsBuffer"].append({
                "ts": get_timestamp(True),
                "pair": position["pair"],
                "initialBalance": position["initialBalance"],
                "endBalance": 0,
                "pnl": position["pnl"],
                "pnl%": 0,
                "step": position["step"],
                "type": "trade"
                })
        algo_data["openPositions"] = []
    # Find and remove position
    else:
        for position in algo_data["openPositions"]:
            if position["id"] == position_id:
                algo_data["pastPositionsBuffer"].append({
                    "ts": get_timestamp(True),
                    "pair": position["pair"],
                    "initialBalance": position["initialBalance"],
                    "endBalance": 0,
                    "pnl": position["pnl"],
                    "pnl%": 0,
                    "step": position["step"],
                    "type": "trade"
                    })
                algo_data["openPositions"] = [p for p in algo_data["openPositions"] if p["id"] != position_id]


###################################### ALGORITHM ############################################
############### THIS SECTION IS NOT COMMENTED TO PROTECT INTELLECTUAL RIGHTS ###############


### Resets algorithm
async def algo_reset():
    global connection_data, asset_data, algo_data

    fibo = 0.61803

    if (len(algo_data["pastPositionsBuffer"]) > 0 and algo_data["pastPositionsBuffer"][-1]["pnl"] > 0) or connection_data["startupFlag"] == True or algo_data["step"] == 7:
        rest_cancel_all()

        if connection_data["startupFlag"] == True:
            while connection_data["closeFlag"]:
                if algo_data["balance"] != asset_data["quote"]["amount"]:
                    algo_data["balance"] = asset_data["quote"]["amount"]
                    algo_data["initialBalance"] = asset_data["quote"]["amount"]
                    break

                await asyncio.sleep(1)
            connection_data["startupFlag"] = False
            connection_data["terminalFlag"] = True
            
        else:
            algo_data["pastPositionsBuffer"][-1]["endBalance"] = algo_data["balance"]
            log_to_csv(algo_data["pastPositionsBuffer"][-1], "tradesLog.csv")  

            algo_data["lastBatch"]["ts"] = get_timestamp(True),
            algo_data["lastBatch"]["pair"] = asset_data["altname"]
            algo_data["lastBatch"]["initialBalance"] = algo_data["initialBalance"]
            algo_data["lastBatch"]["endBalance"] = algo_data["balance"]
            algo_data["lastBatch"]["pnl"] = algo_data["balance"] - algo_data["initialBalance"]
            algo_data["lastBatch"]["pnl%"] = (algo_data["lastBatch"]["pnl"] / algo_data["initialBalance"]) * 100
            algo_data["lastBatch"]["step"] = algo_data["pastPositionsBuffer"][-1]["step"]

            log_to_csv(algo_data["lastBatch"], "tradesLog.csv")

            algo_data["initialBalance"] = algo_data["balance"]
            algo_data["pastPositionsBuffer"] = []

        algo_data["margin"] = algo_data["balance"] * asset_data["leverage"]
        algo_data["positionSize%"] = fibo * 10
        algo_data["positionValue"] =  round(((algo_data["margin"]/100) * algo_data["positionSize%"]), int(asset_data["cost_decimals"]))
        algo_data["positionSize"] = 0
        algo_data["step"] = 0
        algo_data["bought"] = False
        algo_data["limbo%"] = 0.1
        algo_data["tpIncrement"] = 1 + fibo
        algo_data["tp%"] = 1 + fibo
        algo_data["refPrice"] = round(((asset_data["ask"] + asset_data["bid"]) / 2), int(asset_data["pair_decimals"]))
        limboPartial = (algo_data["refPrice"] / 100) * (algo_data["limbo%"] / 2)
        algo_data["longPrice"] = round(((algo_data["refPrice"]) + limboPartial), int(asset_data["pair_decimals"]))
        algo_data["shortPrice"] = round(((algo_data["refPrice"]) - limboPartial), int(asset_data["pair_decimals"]))
        partialTPbuffer = (algo_data["longPrice"] / 100) * algo_data["tp%"]
        algo_data["longTP"] = round((algo_data["longPrice"] + partialTPbuffer), int(asset_data["pair_decimals"]))
        partialTPbuffer = (algo_data["shortPrice"] / 100) * algo_data["tp%"]
        algo_data["shortTP"] = round((algo_data["shortPrice"] - partialTPbuffer), int(asset_data["pair_decimals"]))
        algo_data["type"] = None


### Algorithm step handler
async def algo_stepper():
    global asset_data, connection_data, algo_data

    algo_data["step"] += 1

    if algo_data["step"] > 1:
        algo_data["pastPositionsBuffer"][-1]["endBalance"] = algo_data["balance"]
        log_to_csv(algo_data["pastPositionsBuffer"][-1], "tradesLog.csv")
        await algo_calculator()
    
    if len(algo_data["openPositions"]) == 0 and algo_data["bought"] == False:
        longPositionSize = round((algo_data["positionValue"] / algo_data["longPrice"]), int(asset_data["lot_decimals"]))
        longOrder = rest_open_order(asset_data["altname"], longPositionSize, algo_data["longPrice"], "buy", "stop-loss", algo_data["step"])
        shortPositionSize = round((algo_data["positionValue"] / algo_data["shortPrice"]), int(asset_data["lot_decimals"]))
        shortOrder = rest_open_order(asset_data["altname"], shortPositionSize, algo_data["shortPrice"], "sell", "stop-loss", algo_data["step"])

        while connection_data["closeFlag"]:
            for position in algo_data["openPositions"]:
                if position["id"] == longOrder:
                    rest_cancel_all()
                    algo_data["bought"] = True
                    algo_data["positionSize"] = longPositionSize
                    algo_data["type"] = "buy"
                    rest_open_order(asset_data["altname"], algo_data["positionSize"], algo_data["shortPrice"], "sell", "stop-loss", algo_data["step"])
                    rest_open_order(asset_data["altname"], algo_data["positionSize"], algo_data["longTP"], "sell", "limit", algo_data["step"])
                    break
                elif position["id"] == shortOrder:
                    rest_cancel_all()
                    algo_data["bought"] = True
                    algo_data["positionSize"] = shortPositionSize
                    algo_data["type"] = "sell"
                    rest_open_order(asset_data["altname"], algo_data["positionSize"], algo_data["longPrice"], "buy", "stop-loss", algo_data["step"])
                    rest_open_order(asset_data["altname"], algo_data["positionSize"], algo_data["shortTP"], "buy", "limit", algo_data["step"])
                    break
            
            if algo_data["bought"] == True:
                break

            await asyncio.sleep(1)

        while connection_data["closeFlag"]:
            if len(algo_data["openPositions"]) == 0:
                rest_cancel_all()

                while connection_data["closeFlag"]:
                    if len(algo_data["pendingOrders"]) == 0 and algo_data["balance"] != asset_data["quote"]["amount"] and algo_data["pastPositionsBuffer"][-1]["step"] == algo_data["step"]:
                        algo_data["pastPositionsBuffer"][-1]["pnl"] = asset_data["quote"]["amount"] - algo_data["balance"]
                        algo_data["pastPositionsBuffer"][-1]["endBalance"] = asset_data["quote"]["amount"]
                        algo_data["pastPositionsBuffer"][-1]["pnl%"] = (algo_data["pastPositionsBuffer"][-1]["pnl"] / algo_data["pastPositionsBuffer"][-1]["initialBalance"]) * 100
                        algo_data["balance"] = asset_data["quote"]["amount"]
                        break
                    
                    await asyncio.sleep(1)
                break
            await asyncio.sleep(1)


### Calculates algorithm variables afer step 1
async def algo_calculator():
    global asset_data, algo_data, asset_data

    fibo = 0.61803

    algo_data["margin"] = algo_data["balance"] * asset_data["leverage"]
    algo_data["positionSize%"] += (fibo*(fibo*10))
    algo_data["positionValue"] =  round(((algo_data["margin"]/100) * algo_data["positionSize%"]), int(asset_data["cost_decimals"]))
    algo_data["bought"] = False

    algo_data["limbo%"] *= (fibo + 1)
    tpIncrementBuffer = algo_data["tpIncrement"]
    algo_data["tpIncrement"] *= fibo
    algo_data["tp%"] += tpIncrementBuffer + algo_data["tpIncrement"]

    limboPartial = (algo_data["refPrice"] / 100) * (algo_data["limbo%"] / 2)
    algo_data["longPrice"] = round(((algo_data["refPrice"]) + limboPartial), int(asset_data["pair_decimals"]))
    algo_data["shortPrice"] = round(((algo_data["refPrice"]) - limboPartial), int(asset_data["pair_decimals"]))
    partialTPbuffer = (algo_data["longPrice"] / 100) * algo_data["tp%"]
    algo_data["longTP"] = round((algo_data["longPrice"] + partialTPbuffer), int(asset_data["pair_decimals"]))
    partialTPbuffer = (algo_data["shortPrice"] / 100) * algo_data["tp%"]
    algo_data["shortTP"] = round((algo_data["shortPrice"] - partialTPbuffer), int(asset_data["pair_decimals"]))
    algo_data["type"] = None


### Prints algo data info screen
def terminal_printer():
    global asset_data, algo_data, connection_data
    clear_terminal()

    print(local_time(), f"Server status: {connection_data["serverStatus"]}\n")
    print("LAST BATCH:")
    print(f"    - Start balance: {asset_data["quote"]["altname"]} {algo_data["lastBatch"]["initialBalance"]:.2f} - End balance: {asset_data["quote"]["altname"]} {algo_data["lastBatch"]["endBalance"]:.2f} - PNL: {asset_data["quote"]["altname"]} {algo_data["lastBatch"]["pnl"]:.2f} ({algo_data["lastBatch"]["pnl%"]:.2f}%) - Steps: {algo_data["lastBatch"]["step"]}")
    print(f"\nQUOTE ASSET: {asset_data["quote"]["altname"]} {asset_data['quote']["amount"]:.8f}")
    print(f"BASE ASSET: {asset_data["base"]} - Ask: {asset_data["ask"]} - Bid: {asset_data["bid"]}")
    print("\nALGORITHM DATA")
    print(f"    - Initial Balance: {algo_data["initialBalance"]} - Balance: {algo_data["balance"]:.2f} - Margin: {algo_data["margin"]:.2f} - Leverage: {asset_data["leverage"]}X")
    print(f"    - Step: {algo_data['step']} - Balance %: {algo_data['positionSize%']:.2f}% - Position Value: {algo_data['positionValue']} - Position Volume: {algo_data['positionSize']}")
    print(f"    - Reference price: {algo_data['refPrice']} - Limbo%: {algo_data['limbo%']} - Direction: {algo_data['type']} - Bought: {algo_data['bought']}")
    print(f"    - TakeProfit%: {algo_data['tp%']} - TakeProfit Increment: {algo_data['tpIncrement']}")
    print(f"    - Long Price: {algo_data['longPrice']} - Long TakeProfit: {algo_data['longTP']}")
    print(f"    - Short Price: {algo_data['shortPrice']} - Short TakeProfit: {algo_data['shortTP']}\n")

    print("PAST POSITIONS:")
    for position in algo_data["pastPositionsBuffer"]:
        print(f"    - Pair: {position["pair"]} - Step: {position["step"]} - PnL: {position["pnl"]}")

    print("\nPENDING ORDERS:")
    for order in algo_data["pendingOrders"]:
        print(f"    - Type: {order["type"]} - Step: {order["step"]} - ID: {order["id"]} - Status: {order["status"]}")

    print("\nOPEN POSITIONS:")
    for position in algo_data["openPositions"]:
        print(f"    - Type: {position["type"]} - Step: {position["step"]} - ID: {position["id"]} - Volume: {position["volume"]} - PnL: {position["pnl"]}")

    print("\nERROR LOG:")
    for error in connection_data["errorLog"]:
        print(f"    - {error["error"]}")


    print("\n\nCtrl+Shitf+q to quit - Ctrl+Shitf+c to clear error log")







if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as e:
        sys.exit(e)
