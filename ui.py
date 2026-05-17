"""
UI module consolidating the main application, data viewer, export window, and widgets.
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime
import threading
import pandas as pd
import logging

logger = logging.getLogger(__name__)

# Try to import tkcalendar for DateEntry
try:
    from tkcalendar import DateEntry  # type: ignore[import]
except ImportError:
    DateEntry = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Widgets (formerly widgets.py)
# ---------------------------------------------------------------------------
if DateEntry is None:
    # Fallback implementation of DateEntry
    class DateEntry(ttk.Entry):
        def __init__(self, master=None, **kwargs):
            date_pattern = kwargs.pop('date_pattern', 'yyyy-mm-dd')
            kwargs.pop('background', None)
            kwargs.pop('foreground', None)
            kwargs.pop('borderwidth', None)
            super().__init__(master, **kwargs)
            self.date_pattern = date_pattern
            self.insert(0, datetime.now().strftime('%Y-%m-%d'))

        def set_date(self, date_obj):
            if isinstance(date_obj, datetime):
                date_str = date_obj.strftime('%Y-%m-%d')
            elif isinstance(date_obj, str):
                date_str = date_obj
            else:
                try:
                    date_str = date_obj.strftime('%Y-%m-%d')
                except:
                    date_str = str(date_obj)
            self.delete(0, tk.END)
            self.insert(0, date_str)

        def get_date(self):
            date_str = self.get()
            try:
                return datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                messagebox.showerror("Error", f"Invalid date: {date_str}. Expected format: YYYY-MM-DD")
                return datetime.now().date()

# ---------------------------------------------------------------------------
# Data Viewer (formerly data_viewer.py)
# ---------------------------------------------------------------------------
from core import get_data

class DataViewerWindow(tk.Toplevel):
    def __init__(self, parent, ticker, timeframe):
        super().__init__(parent)
        self.title(f"Data Viewer: {ticker} ({timeframe})")
        self.geometry("1200x600")
        self.ticker = ticker
        self.timeframe = timeframe
        self._init_ui()
        self._load_data()

    def _init_ui(self):
        frame = ttk.Frame(self, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text=f"Ticker: {self.ticker}, TF: {self.timeframe}", font=('Arial', 10, 'bold')).pack(anchor=tk.W, pady=(0, 10))

        # Expanded columns list
        columns = [
            'time', 'price_open', 'price_close', 'price_high', 'price_low', 'volume',
            'oi_open_coin', 'oi_high_coin', 'oi_low_coin', 'oi_close_coin',
            'liq_long_coin', 'liq_short_coin', 'taker_buy_base', 'mark_price',
            'index_price', 'funding_rate', 'oi_binance', 'ls_ratio',
            'top_ls_ratio', 'taker_vol_ratio'
        ]
        self.tree = ttk.Treeview(frame, columns=columns, show='headings')
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=120 if col == 'time' else 90)

        y_scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.tree.yview)
        x_scroll = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        y_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        x_scroll.pack(side=tk.BOTTOM, fill=tk.X)

    def _load_data(self):
        try:
            df = get_data(self.ticker, self.timeframe)
            if df.empty: return
            for _, row in df.iterrows():
                vals = [f"{row.get(col):.8f}" if col == 'funding_rate' and isinstance(row.get(col), (float, int)) else f"{row.get(col):.4f}" if isinstance(row.get(col), (float, int)) else row.get(col) for col in self.tree['columns']]
                self.tree.insert('', tk.END, values=vals)
            self.title(f"Data Viewer: {self.ticker} ({self.timeframe}) - Total {len(df)} records")
        except Exception as e:
            print(f"Error loading data viewer: {e}")

# ---------------------------------------------------------------------------
# Export Window (formerly export_window.py)
# ---------------------------------------------------------------------------
from core import get_available_tickers, get_earliest_timestamp, get_latest_timestamp, export_to_csv

class ExportWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Export Data")
        self.geometry("700x600")
        self.transient(parent)
        self.grab_set()
        self.parent = parent
        self.available_data = get_available_tickers()
        self._init_ui()

    def _init_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        main_frame = ttk.Frame(self, padding="10")
        main_frame.grid(row=0, column=0, sticky="nsew")
        main_frame.columnconfigure(0, weight=1)

        source_frame = ttk.LabelFrame(main_frame, text="Data Source", padding="10")
        source_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(source_frame, text="Ticker:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.ticker_var = tk.StringVar()
        self.ticker_combo = ttk.Combobox(source_frame, textvariable=self.ticker_var, state="readonly")
        tickers = sorted(list(set([t for t, _ in self.available_data])))
        self.ticker_combo['values'] = tickers
        self.ticker_combo.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        self.ticker_combo.bind("<<ComboboxSelected>>", self._on_ticker_change)
        ttk.Label(source_frame, text="Timeframe:").grid(row=0, column=2, sticky=tk.W, padx=5, pady=5)
        self.tf_var = tk.StringVar()
        self.tf_combo = ttk.Combobox(source_frame, textvariable=self.tf_var, state="readonly")
        self.tf_combo.grid(row=0, column=3, sticky=tk.W, padx=5, pady=5)
        self.tf_combo.bind("<<ComboboxSelected>>", self._update_date_range_info)

        date_frame = ttk.LabelFrame(main_frame, text="Data Period", padding="10")
        date_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        self.range_info_label = ttk.Label(date_frame, text="Select ticker and timeframe", foreground="gray")
        self.range_info_label.pack(pady=5)
        date_input_frame = ttk.Frame(date_frame)
        date_input_frame.pack(fill=tk.X, pady=5)
        ttk.Label(date_input_frame, text="Start date:").pack(side=tk.LEFT, padx=5)
        self.start_date_entry = DateEntry(date_input_frame, width=12, background='darkblue', foreground='white', borderwidth=2, date_pattern='yyyy-mm-dd')
        self.start_date_entry.pack(side=tk.LEFT, padx=5)
        ttk.Label(date_input_frame, text="End date:").pack(side=tk.LEFT, padx=5)
        self.end_date_entry = DateEntry(date_input_frame, width=12, background='darkblue', foreground='white', borderwidth=2, date_pattern='yyyy-mm-dd')
        self.end_date_entry.pack(side=tk.LEFT, padx=5)

        cols_frame = ttk.LabelFrame(main_frame, text="Column Selection", padding="10")
        cols_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 10))
        main_frame.rowconfigure(2, weight=1)

        # Expanded columns list based on requirements
        self.all_columns = [
            'time', 'price_open', 'price_close', 'price_high', 'price_low', 'volume',
            'oi_open_coin', 'oi_high_coin', 'oi_low_coin', 'oi_close_coin',
            'liq_long_coin', 'liq_short_coin', 'taker_buy_base', 'mark_price',
            'index_price', 'funding_rate', 'oi_binance', 'ls_ratio',
            'top_ls_ratio', 'taker_vol_ratio'
        ]
        self.col_vars = {}
        for i, col in enumerate(self.all_columns):
            var = tk.BooleanVar(value=True)
            self.col_vars[col] = var
            ttk.Checkbutton(cols_frame, text=col, variable=var).grid(row=i//2, column=i%2, sticky=tk.W, padx=20, pady=2)
        select_btn_frame = ttk.Frame(cols_frame)
        select_btn_frame.grid(row=10, column=0, columnspan=2, sticky=tk.E, pady=10)
        ttk.Button(select_btn_frame, text="Select All", command=self._select_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(select_btn_frame, text="Deselect All", command=self._deselect_all).pack(side=tk.LEFT, padx=5)
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=3, column=0, sticky="ew", pady=10)
        ttk.Button(btn_frame, text="Export", command=self._export).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side=tk.RIGHT, padx=5)

    def _on_ticker_change(self, event):
        ticker = self.ticker_var.get()
        tfs = sorted([tf for t, tf in self.available_data if t == ticker])
        self.tf_combo['values'] = tfs
        if tfs:
            self.tf_combo.current(0)
            self._update_date_range_info()

    def _update_date_range_info(self, event=None):
        ticker, tf = self.ticker_var.get(), self.tf_var.get()
        if not ticker or not tf: return
        earliest, latest = get_earliest_timestamp(ticker, tf), get_latest_timestamp(ticker, tf)
        if earliest and latest:
            self.range_info_label.config(text=f"Available range:\n{earliest} — {latest}")
            self.start_date_entry.set_date(earliest)
            self.end_date_entry.set_date(latest)
        else:
            self.range_info_label.config(text="No data")

    def _select_all(self):
        for var in self.col_vars.values(): var.set(True)
    def _deselect_all(self):
        for var in self.col_vars.values(): var.set(False)

    def _export(self):
        ticker, tf = self.ticker_var.get(), self.tf_var.get()
        start, end = self.start_date_entry.get_date(), self.end_date_entry.get_date()
        start_dt = datetime.combine(start, datetime.min.time())
        end_dt = datetime.combine(end, datetime.max.time())
        if not ticker or not tf:
            messagebox.showerror("Error", "Select ticker and timeframe")
            return
        selected_cols = [col for col, var in self.col_vars.items() if var.get()]
        if not selected_cols:
            messagebox.showerror("Error", "Select at least one column")
            return
        filename = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv"), ("All files", "*.csv")], initialfile=f"{ticker}_{tf}_{start}_{end}.csv")
        if filename:
            logger.info(f"User exporting {ticker} ({tf}) from {start} to {end}. Columns: {selected_cols}. Filename: {filename}")
            if export_to_csv(ticker, tf, start_dt, end_dt, selected_cols, filename):
                messagebox.showinfo("Success", f"Data exported to\n{filename}")
                self.destroy()
            else:
                messagebox.showerror("Error", "Failed to export data")

# ---------------------------------------------------------------------------
# Main App (formerly app.py)
# ---------------------------------------------------------------------------
from core import download_multiple, get_data_summary, delete_data, get_available_tickers, get_latest_timestamp, download_data, get_missing_metrics_start

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Data Management Tool")
        self.geometry("1000x700")
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("Green.Horizontal.TProgressbar", background='#06b025', troughcolor='#e6e6e6')
        self._init_ui()
        self._refresh_data()

    def _init_ui(self):
        load_frame = ttk.LabelFrame(self, text="Load Parameters", padding="10")
        load_frame.pack(fill=tk.X, padx=10, pady=5)
        load_frame.columnconfigure(1, weight=1)
        ttk.Label(load_frame, text="Tickers (comma-separated):").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.tickers_entry = ttk.Entry(load_frame)
        self.tickers_entry.insert(0, "BTCUSDT,ETHUSDT")
        self.tickers_entry.grid(row=0, column=1, sticky=tk.EW, pady=2)
        ttk.Label(load_frame, text="Timeframes (comma-separated):").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.tfs_entry = ttk.Entry(load_frame)
        self.tfs_entry.insert(0, "1h,4h,1d")
        self.tfs_entry.grid(row=1, column=1, sticky=tk.EW, pady=2)
        ttk.Label(load_frame, text="Available: 1m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d", foreground="gray").grid(row=2, column=1, sticky=tk.W)
        ttk.Label(load_frame, text="Start date:").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.start_date_entry = DateEntry(load_frame, width=12, background='darkblue', foreground='white', borderwidth=2, date_pattern='yyyy-mm-dd')
        self.start_date_entry.set_date(datetime(datetime.now().year, 1, 1))
        self.start_date_entry.grid(row=3, column=1, sticky=tk.W, pady=2)
        ttk.Label(load_frame, text="End date:").grid(row=4, column=0, sticky=tk.W, pady=2)
        self.end_date_entry = DateEntry(load_frame, width=12, background='darkblue', foreground='white', borderwidth=2, date_pattern='yyyy-mm-dd')
        self.end_date_entry.set_date(datetime.now())
        self.end_date_entry.grid(row=4, column=1, sticky=tk.W, pady=2)
        btn_frame = ttk.Frame(load_frame)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=10, sticky=tk.W)
        self.load_btn = ttk.Button(btn_frame, text="Load Data", command=self._start_download)
        self.load_btn.pack(side=tk.LEFT)
        self.update_btn = ttk.Button(btn_frame, text="Update Data", command=self._start_update_all)
        self.update_btn.pack(side=tk.LEFT, padx=(10, 0))
        self.progress_var = tk.StringVar()
        self.progress_label = ttk.Label(load_frame, textvariable=self.progress_var)
        self.progress_label.grid(row=6, column=0, columnspan=2, sticky=tk.W, pady=(0, 2))
        self.progress_bar = ttk.Progressbar(load_frame, mode='determinate', length=400, style="Green.Horizontal.TProgressbar")
        self.progress_bar.grid(row=7, column=0, columnspan=2, sticky=tk.W, pady=(0, 5))
        self.progress_bar.grid_remove()
        table_frame = ttk.LabelFrame(self, text="Database Records", padding="10")
        table_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        cols = ('ticker', 'tf', 'start', 'end', 'count')
        self.tree = ttk.Treeview(table_frame, columns=cols, show='headings')
        for c in cols: self.tree.heading(c, text=c if c != 'tf' else 'TF')
        self.tree.column('ticker', width=100); self.tree.column('tf', width=50); self.tree.column('start', width=150); self.tree.column('end', width=150); self.tree.column('count', width=80, anchor=tk.E)
        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        action_frame = ttk.Frame(self, padding="10")
        action_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Button(action_frame, text="Refresh Table", command=self._refresh_data).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="View Data", command=self._open_data_viewer).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="Delete Data", command=self._delete_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="Export Data", command=self._open_export_window).pack(side=tk.LEFT, padx=5, fill=tk.X)

    def _open_data_viewer(self):
        selected = self.tree.selection()
        if not selected:
             messagebox.showinfo("Info", "Select a data row to view")
             return
        item = self.tree.item(selected[0])
        vals = item['values']
        ticker, tf = vals[0], vals[1]
        logger.info(f"User opened Data Viewer for {ticker} ({tf})")
        DataViewerWindow(self, ticker, tf)

    def _refresh_data(self):
        for item in self.tree.get_children(): self.tree.delete(item)
        for row in get_data_summary():
            self.tree.insert('', tk.END, values=(row['ticker'], row['timeframe'], row['start_time'], row['end_time'], row['count']))

    def _active_download_ui(self, active: bool):
        state = tk.DISABLED if active else tk.NORMAL
        self.load_btn.config(state=state)
        self.update_btn.config(state=state)
        if active:
            self.progress_var.set("Starting download...")
            self.progress_bar['value'] = 0
            self.progress_bar.grid()
        else:
            self.progress_var.set("Done.")
            self.progress_bar.grid_remove()
            self.progress_bar['value'] = 0

    def _start_download(self):
        tickers_str, tfs_str = self.tickers_entry.get(), self.tfs_entry.get()
        if not tickers_str or not tfs_str:
            messagebox.showerror("Error", "Enter tickers and timeframes")
            return
        tickers = [t.strip().upper() for t in tickers_str.split(',') if t.strip()]
        tfs = [t.strip() for t in tfs_str.split(',') if t.strip()]
        start_date = datetime.combine(self.start_date_entry.get_date(), datetime.min.time())
        end_date = datetime.combine(self.end_date_entry.get_date(), datetime.max.time())

        logger.info(f"User started download: tickers={tickers}, tfs={tfs}, start={start_date}, end={end_date}")

        self._active_download_ui(True)
        thread = threading.Thread(target=self._download_task, args=(tickers, tfs, start_date, end_date))
        thread.daemon = True
        thread.start()

    def _download_task(self, tickers, tfs, start_date, end_date):
        def progress_cb(msg, percentage=0):
            def _update():
                if msg: self.progress_var.set(msg)
                if percentage >= 0: self.progress_bar['value'] = percentage
            self.after(0, _update)
        try:
            download_multiple(tickers=tickers, timeframes=tfs, start_date=start_date, end_date=end_date, progress_callback=progress_cb, incremental=False)
            self.after(0, lambda: messagebox.showinfo("Done", "Download completed"))
        except Exception as e:
            error_msg = str(e)
            self.after(0, lambda msg=error_msg: messagebox.showerror("Error", msg))
        finally:
            self.after(0, lambda: self._active_download_ui(False))
            self.after(0, self._refresh_data)

    def _update_all_task(self, pairs):
        def progress_cb(msg: str, percentage: int | float = -1):
            def _update():
                if msg: self.progress_var.set(msg)
                if percentage >= 0: self.progress_bar['value'] = int(percentage)
            self.after(0, _update)
        total = len(pairs)
        errors = []
        try:
            for idx, (ticker, timeframe) in enumerate(pairs, 1):
                base_pct = ((idx - 1) / total) * 100
                progress_cb(f"Updating [{idx}/{total}] {ticker} {timeframe}...", base_pct)
                def sub_progress(msg, sub_pct=0):
                    overall_pct = base_pct + ((sub_pct / 100) * (100 / total))
                    progress_cb(msg, overall_pct)
                latest = get_latest_timestamp(ticker, timeframe)
                missing_start = get_missing_metrics_start(ticker, timeframe)

                # Smart start date: if some metrics are missing, download from their earliest missing point
                if missing_start and (not latest or missing_start < latest):
                    start_for_download = missing_start
                    is_incremental = False  # Force history backfill
                    progress_cb(f"Backfilling empty columns from {missing_start.date()}...", base_pct)
                else:
                    start_for_download = latest
                    is_incremental = True

                if start_for_download:
                    try:
                        download_data(ticker=ticker, timeframe=timeframe, start_date=start_for_download, end_date=datetime.now(), progress_callback=sub_progress, incremental=is_incremental)
                    except Exception as e:
                        errors.append(f"{ticker} {timeframe}: {e}")
                        progress_cb(f"Error: {ticker} {timeframe}: {e}", base_pct)
                else:
                    progress_cb(f"No data for {ticker} {timeframe}", base_pct)
        except Exception as e:
            error_msg = str(e)
            self.after(0, lambda msg=error_msg: messagebox.showerror("Error", msg))
        finally:
            self.after(0, lambda: self._active_download_ui(False))
            self.after(0, self._refresh_data)

    def _start_update_all(self):
        """Update all existing data in the DB to the latest available moment."""
        pairs = get_available_tickers()
        if not pairs:
            messagebox.showinfo("Info", "No data in database to update.")
            return
        logger.info(f"User started updating all data. Found {len(pairs)} pairs to update.")
        self._active_download_ui(True)
        self.progress_var.set("Updating all data...")
        thread = threading.Thread(target=self._update_all_task, args=(pairs,))
        thread.daemon = True
        thread.start()

    def _delete_selected(self):
        selected = self.tree.selection()
        if not selected: return
        if not messagebox.askyesno("Confirm", "Delete selected data?"): return

        for item in selected:
            vals = self.tree.item(item)['values']
            ticker, tf = vals[0], vals[1]
            logger.info(f"User deleted data for {ticker} ({tf})")
            delete_data(ticker, tf)
        self._refresh_data()

    def _open_export_window(self):
        ExportWindow(self)

if __name__ == "__main__":
    app = App()
    app.mainloop()
