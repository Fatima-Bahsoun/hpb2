import sqlite3
import pandas as pd
import streamlit as st

# Page Configuration
st.set_page_config(
    page_title="HPB Used Book Inventory Dashboard", layout="wide"
)

st.title("📚 HPB Used Book Inventory Dashboard")


# Load data from SQLite database
@st.cache_data(ttl=10)
def load_data():
  conn = sqlite3.connect("hpb_inventory.db")
  query = "SELECT * FROM inventory_logs"
  df = pd.read_sql(query, conn)
  conn.close()
  return df


df = load_data()

if df.empty:
  st.warning(
      "No inventory data found in `hpb_inventory.db`. Run your scraper first!"
  )
else:
  # Get unique timestamps sorted chronologically (newest first)
  timestamps = sorted(df["timestamp"].unique(), reverse=True)

  # Sidebar Controls
  st.sidebar.header("Dashboard Controls")
  diff_scope = st.sidebar.radio(
      "Diff Comparison Scope",
      ["Last Run Only (Default)", "All Previous Runs (Cumulative)"],
  )

  if len(timestamps) < 2:
    st.warning(
        "Only one run found in the database. Need at least two runs to"
        " calculate added/sold diffs."
    )
    view_df = df[df["timestamp"] == timestamps[0]].copy()
    view_df["status"] = "exists"
  else:
    latest_timestamp = timestamps[0]
    latest_df = df[df["timestamp"] == latest_timestamp].copy()

    if diff_scope == "Last Run Only (Default)":
      # Standard comparison: Latest vs Immediate Previous Run
      prev_timestamp = timestamps[1]
      prev_df = df[df["timestamp"] == prev_timestamp]

      latest_keys = set(zip(latest_df["usedSku"], latest_df["storeName"]))
      prev_keys = set(zip(prev_df["usedSku"], prev_df["storeName"]))

      added_keys = latest_keys - prev_keys
      sold_keys = prev_keys - latest_keys

      def get_status(row):
        key = (row["usedSku"], row["storeName"])
        if key in added_keys:
          return "added"
        elif key in sold_keys:
          return "sold"
        else:
          return "exists"

      latest_df["status"] = latest_df.apply(get_status, axis=1)

      # Include sold items from the previous run for visibility
      sold_rows = prev_df[
          prev_df.apply(
              lambda r: (r["usedSku"], r["storeName"]) in sold_keys, axis=1
          )
      ].copy()
      sold_rows["status"] = "sold"
      view_df = pd.concat([latest_df, sold_rows], ignore_index=True)

    else:
      # Cumulative comparison: Latest vs ALL Past Runs combined
      past_df = df[df["timestamp"] != latest_timestamp]

      latest_keys = set(zip(latest_df["usedSku"], latest_df["storeName"]))
      all_past_keys = set(zip(past_df["usedSku"], past_df["storeName"]))

      added_keys = latest_keys - all_past_keys
      sold_keys = all_past_keys - latest_keys

      def get_cumulative_status(row):
        key = (row["usedSku"], row["storeName"])
        if key in added_keys:
          return "added"
        else:
          return "exists"

      latest_df["status"] = latest_df.apply(get_cumulative_status, axis=1)

      # Pull the latest known record of items that sold out at some point in history
      sold_rows = (
          past_df[
              past_df.apply(
                  lambda r: (r["usedSku"], r["storeName"]) in sold_keys, axis=1
              )
          ]
          .sort_values("timestamp")
          .drop_duplicates(subset=["usedSku", "storeName"], keep="last")
          .copy()
      )
      sold_rows["status"] = "sold"
      view_df = pd.concat([latest_df, sold_rows], ignore_index=True)

  # Sidebar Filters
  st.sidebar.divider()
  status_filter = st.sidebar.multiselect(
      "Filter by Status",
      ["added", "exists", "sold"],
      default=["added", "exists", "sold"],
  )
  if status_filter:
    view_df = view_df[view_df["status"].isin(status_filter)]

  search_query = st.sidebar.text_input("Search Title or Store")
  if search_query:
    view_df = view_df[
        view_df["title"].str.contains(search_query, case=False, na=False)
        | view_df["storeName"].str.contains(search_query, case=False, na=False)
    ]

  # Clean and format columns explicitly to prevent alignment shifts
  display_df = view_df[
      [
          "status",
          "title",
          "price",
          "usedSku",
          "storeName",
          "city",
          "state",
          "distanceMiles",
          "qty",
          "timestamp",
      ]
  ].copy()

  display_df["distanceMiles"] = (
      pd.to_numeric(display_df["distanceMiles"], errors="coerce")
      .fillna(0)
      .round()
      .astype(int)
  )
  display_df["qty"] = pd.to_numeric(display_df["qty"], errors="coerce").fillna(
      1
  )
  display_df["price"] = display_df["price"].astype(str).str.strip()

    # Assuming your dataframe is named 'df' and the timestamp column is 'timestamp'
  # 1. Convert string to datetime
  display_df['timestamp'] = pd.to_datetime(display_df['timestamp'])

  # 2. Handle timezone conversion safely (localizing only if naive, or converting directly if already aware)
  if display_df['timestamp'].dt.tz is None:
      display_df['timestamp_cst'] = display_df['timestamp'].dt.tz_localize('UTC').dt.tz_convert('America/Chicago')
  else:
      display_df['timestamp_cst'] = display_df['timestamp'].dt.tz_convert('America/Chicago')

  # 3. Format into: Day mm/dd/yy hh:mm (e.g., Sun 11/01/26 09:30)
  display_df['timestamp'] = display_df['timestamp_cst'].dt.strftime('%a %m/%d/%y %H:%M')

  # Apply color styling using .map() (compatible with modern pandas)
  def color_status(val):
    if val == "added":
      return "background-color: #d4edda; color: #155724; font-weight: bold;"
    elif val == "sold":
      return "background-color: #f8d7da; color: #721c24; font-weight: bold;"
    else:
      return "background-color: #e2e3e5; color: #383d41;"


  styled_df = display_df.style.map(color_status, subset=["status"])

  # Calculate dynamic height based on row count (approx 35px per row, capped at 650px max)
  num_rows = len(display_df)
  table_height = min(650, max(250, (num_rows + 1) * 35))

  st.subheader(f"Inventory Results ({num_rows} rows)")
  st.dataframe(
      styled_df,
      use_container_width=True,
      hide_index=True,
      height=table_height,
  )
