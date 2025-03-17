     /$$$$$$$$ /$$ /$$                 /$$   /$$                 /$$
    | $$_____/|__/| $$                | $$  | $$                | $$
    | $$       /$$| $$$$$$$   /$$$$$$ | $$  | $$  /$$$$$$   /$$$$$$$  /$$$$$$   /$$$$$$   /$$$$$$
    | $$$$$   | $$| $$__  $$ /$$__  $$| $$$$$$$$ /$$__  $$ /$$__  $$ /$$__  $$ /$$__  $$ /$$__  $$
    | $$__/   | $$| $$  \ $$| $$  \ $$| $$__  $$| $$$$$$$$| $$  | $$| $$  \ $$| $$$$$$$$| $$  \__/
    | $$      | $$| $$  | $$| $$  | $$| $$  | $$| $$_____/| $$  | $$| $$  | $$| $$_____/| $$
    | $$      | $$| $$$$$$$/|  $$$$$$/| $$  | $$|  $$$$$$$|  $$$$$$$|  $$$$$$$|  $$$$$$$| $$
    |__/      |__/|_______/  \______/ |__/  |__/ \_______/ \_______/ \____  $$ \_______/|__/
                                                                     /$$  \ $$\
                                                                     |  $$$$$$/
                                                                      \______/




# DISCLAIMER

FiboHedger is an open-source experimental software, and the author does not take any responsibility for its usage. Users should understand the following:

Cryptocurrency trading carries inherent risks, and users should only engage with funds they can afford to lose. FiboHedger does not provide financial advice, and users should seek guidance from a qualified financial advisor before trading.

Users are solely responsible for managing their risk exposure while using FiboHedger. This includes implementing appropriate risk management strategies and choosing proper algorithm settings.

The author of FiboHedger is not liable for any damages or losses resulting from the use of the software. Users are expected to comply with all applicable laws and regulations governing cryptocurrency trading in their respective jurisdictions.

By using FiboHedger, users acknowledge and accept these terms and agree to use the software at their own risk.



# WHAT IS FiboHedger?

FiboHedger is an open-source experimental algorithm for the Kraken exchange, its design is based on a hedging mathematical model which balances long and short positions to ensure that gains consistently outweigh losses. Here's a good video explanation by EcoEngineering (https://www.youtube.com/watch?v=NGBPq_CSha8) which explains the basic technique, or scroll to the "How the algorithm works" section for a quicker explanation. This hedging technique has been tweaked with the Fibonacci sequence, from which hence the name.

FiboHedger only works on spot wallet with a maximum of 5X leverage and at least 20$ equivalent of quote asset (subject to change based on quote asset, location and minimum order).



# SYSTEM REQUIREMENTS

## Hardware

While minimum system specifications may vary depending on the underlying operating system, a very important requirement is a stable internet connection, as this affects slippage and therefore profit.
The smallest system this script has been tested on is a Ubuntu VPS with 2gb of RAM.

## Software:

FiboHedger depends on the 'websockets', 'requests', 'pycountry' and 'pynput'. Libraries are checked and installed automatically on first start.
On First start, will also be created the folders '/login_credentials' and '/log':
- In the '/login_credentials' folder there are two .txt files:
	- 'apikey.txt' stores the Kraken exchange API key
	- 'private_key.txt' stores the Kraken exchange private key
- In the '/log' folder there are two .csv files:
	- 'errorLog.csv' stores software and connection errors with timestamp (for debugging)
	- 'tradesLog.csv' stores the trades history, which can be copied and analysed. 



# HOW TO LOGIN

First, you'll need a Kraken API with trading permission (just don't tick 'withdrawals' and your funds will be safe), please refer to Kraken's documentation on how to do that.
Once done, you'll have an API key and a private key, which you'll need to paste into terminal on first usage.

ATTENTION, these will be stored IN CLEAR into the '/login_credentials' folder, so remember to delete the files (and empty the trash folder) if you want to delete API credentials. 



# INPUTS

## API key and Private key

These are only asked if files inside '/login_credentials' are empty or don't exist (they get re-created automatically)
ATTENTION, you'll not see the pasted text, be careful not to paste multiple times.

## Available currencies

Looks like this:

	Available currencies:
	1 - USDT - Amount: 0.00002500
	2 - GBP - Amount: 0.0017
	3 - USD - Amount: 47.3758

	Select a quote currency [1, 3]: 

Enter the menu item to select the quote coin.

## Leverage

Looks like this:

	Enter a leverage to filter tradable assets (1-5):

The leverage must be between 1 (no leverage) and 5 (5X), based on this only the assets available with the chosen leverage will be listed when selecting the base asset.

## Country code and regional subcode

Looks like this:

	Enter a country code to filer tradable assets
	(type 'list' to list all, leave empty for no coutry filter): gb
	Country selected:  United Kingdom

	Enter a regional subcode to filer tradable assets
	(type 'list' to list all, leave empty for no regional subcode filter):

The country filter is useful to filter base assets that are actually available in the country you're connecting from.
The regional subcode is usually not needed, apart from special financial jurisdictions like the New York State, USA.

## Base asset

If less than 10 available assets, looks like this:

	Available assets:
	1 - XDG
	2 - ETH
	3 - XBT
	4 - XRP

	Select a base asset [1, 4]:

And you'll have to input the menu item of the base asset you want to trade.

If 10 or more available assets, it looks like this:

	Search base asset (372 assets found)
	('list all' to list all assets)
	Search: 

And you'll have to enter precisely a base asset to select it, a partial asset to get suggestions or 'list all' to get the full list.

In example:

	BT: invalid asset, did you mean:

	XBT
	BTT
	BNT
	BMT
	BIT
	BAT
	WBTC
	TBTC
	T

	Search base asset (372 assets found)
	('list all' to list all assets)
	Search: 

## RECAP
Looks like this:

	RECAP:
	   Symbol: XRP/USD
	   Leverage: 5
	   Budget: 47.3758 USD
	   Leveraged margin: 236.879 USD

	Do you want to proceed? (y/n):

Enter 'y' to start algorithm or 'n' to exit program.



# HOW THE ALGORITHM WORKS

This hedging mathematical model opens orders in opposite directions so to make profits in either direction.
For a basic explaination of how hedging works, have a look at the video explanation by EcoEngineering here --> https://www.youtube.com/watch?v=NGBPq_CSha8

At every step, two orders are open in both directions with a higher distance between each other, higher volume and higher take-profit.
When one of these two orders gets filled, the other one becomes a stop-loss.
If the position ends at loss, the algorithm proceeds to the next step with higher distance, volume and take-profit
If the position ends at win the algorithm resets and the profits from the last winning trade are always greater than the sum of the losses from the previous losing trades.

A series of trades is called a batch, and after 7 steps the algorithm resets regardless to avoid excessive losses. All algorithmic measures increments are based on Fractal mathematics.

### From the interface it looks like this:

	2025-03-17 09:59:52 - Server status: online

	LAST BATCH:
		- Start balance: USD 45.5802 - End balance: USD 47.3758 - PNL: USD 1.7956 (3.94%) - Steps: 7

	QUOTE ASSET: USD 44.4478
	BASE ASSET: XRP - Ask: 2.3476 - Bid: 2.34759

	ALGORITHM DATA
		- Initial Balance: 47.38 - Balance: 47.38 - Margin: 236.88 - Leverage: 5X
		- Step: 1 - Balance %: 6.18% - Position Value: 14.63983284 - Position Volume: 6.23510217
		- Reference price: 2.3468 - Limbo%: 0.1 - Direction: buy - Bought: True
		- TakeProfit%: 1.61803 - TakeProfit Increment: 1.61803
		- Long Price: 2.34797 - Long TakeProfit: 2.38596
		- Short Price: 2.34563 - Short TakeProfit: 2.30768

	PAST POSITIONS:

	PENDING ORDERS:
		- Type: sell - Step: 1 - ID: OSMQZL-MAZRU-ZH7QNI - Status: ok
		- Type: sell - Step: 1 - ID: OMGNGH-WDYT7-CJSV4S - Status: ok

	OPEN POSITIONS:
		- Type: buy - Step: 1 - ID: OBHFGU-A3XUE-B5QV7D - Volume: 6.23510217 - PnL: -0.0066

	ERROR LOG:
		- EAPI:Invalid nonce


	Ctrl+Shitf+q to quit - Ctrl+Shitf+c to clear error log

Upon starting the algorithm, the first calculation is Reference price, which is simply calculated from the ask and bid: (ask+bid)/2. It can be considered the starting current price that will be used to calculate the other four price levels, listed below in order of value in the same way you'd see them on a trading chart:

- **Long TakeProfit**: take profit for the long position.
- **Long Price**: price at which the long position is open and stop-loss for the short position.
- **Reference price**: middle price upon which all other price levels are calculated.
- **Short Price**: price at which the short position is open and stop-loss for the long position.
- **Short TakeProfit**: take profit for the short position.

Also, the limbo is the space between long and short price.

## Algorithm issues [IMPORTANT]

Even if the algorithm is coded to limit losses, losses are still likely to accurr. Also, please take into consideration that this algorithm is experimental and UNTESTED.

**THIS IS AN EXPERIMENTAL ALGORITHM AND YOU ARE LIKELY TO LOSE MONEY WITH IT.**

**USE IT AT YOUR OWN RISK.**