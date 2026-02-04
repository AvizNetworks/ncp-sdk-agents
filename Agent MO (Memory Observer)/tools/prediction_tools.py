import json
from ncp import tool
import pandas as pd

import json
import requests
from datetime import datetime, timedelta

@tool
def predict_device_memory_xgboost(device_mac: str, training_hours = 168, prediction_days: float = 1.0):
    try:
        import xgboost
        from xgboost import XGBRegressor
        import numpy as np
        from .agent_mo_tools import BASE_URL_ONES, USERNAME_ONES, PASSWORD_ONES, login

    except ImportError:
        return {"status": "error", "message": "xgboost is not installed."}
    """
    Predicts memory usage for a configurable future duration using API data.

    Args:
        device_mac (str): MAC address of the device.
        training_hours (int): Hours of history to fetch for training.
        prediction_days (float): How many days into the future to predict.
    """

    # ---------------------------------------------------------
    # 1. Fetch Data from API
    # ---------------------------------------------------------
    BASE_URL = BASE_URL_ONES
    USERNAME = USERNAME_ONES
    PASSWORD = PASSWORD_ONES

    token = login(BASE_URL, USERNAME, PASSWORD)
    if not token:
        return {"status": "error", "message": "Authentication failed."}

    end_dt = datetime.now()
    start_dt = end_dt - timedelta(hours=training_hours)
    fmt = "%Y-%m-%d %H:%M:%S"

    headers = {"authorization": token, "accept": "application/json"}
    filter_params = {
        "fromDate": start_dt.strftime(fmt),
        "toDate": end_dt.strftime(fmt),
        "windowSize": "1 hour",
        "deviceAddress": device_mac,
        "activeTab": "system"
    }

    try:
        url = f"{BASE_URL}/api/health/mega"
        response = requests.get(url, headers=headers, params={"filter": json.dumps(filter_params)}, verify=False)
        response.raise_for_status()
        api_data = response.json()
        mem_util_list = api_data.get("memUtil", [])
        if not mem_util_list or "data" not in mem_util_list[0]:
            return {"status": "error", "message": "No memory utilization data found."}
        raw_data = mem_util_list[0]["data"]  # List of [timestamp, value]
        df = pd.DataFrame(raw_data, columns=['time', 'mem_util'])
        df['time'] = pd.to_datetime(df['time'], unit='ms')
        if df.empty or len(df) < 30:
            return {"status": "error", "message": f"Not enough data. Found {len(df)} rows, need > 30."}
    except Exception as e:
        return {"status": "error", "message": f"API error: {str(e)}"}

    # ---------------------------------------------------------
    # 2. Train Model
    # ---------------------------------------------------------
    df['hour'] = df['time'].dt.hour
    df['minute'] = df['time'].dt.minute
    df['dayofweek'] = df['time'].dt.dayofweek

    df['lag_1'] = df['mem_util'].shift(1)
    df['lag_2'] = df['mem_util'].shift(2)
    df['lag_3'] = df['mem_util'].shift(3)

    train_df = df.dropna()
    X = train_df[['hour', 'minute', 'dayofweek', 'lag_1', 'lag_2', 'lag_3']]
    y = train_df['mem_util']

    model = XGBRegressor(objective='reg:squarederror', n_estimators=100, max_depth=5)
    model.fit(X, y)

    # ---------------------------------------------------------
    # 3. Recursive Forecasting Loop
    # ---------------------------------------------------------
    steps_to_predict = int((prediction_days * 24 * 60) / 6)
    last_row = df.iloc[-1]
    current_lag_1 = last_row['mem_util']
    current_lag_2 = last_row['lag_1']
    current_lag_3 = last_row['lag_2']
    current_time = last_row['time']

    predictions = []

    for _ in range(steps_to_predict):
        next_time = current_time + timedelta(minutes=6)
        features = pd.DataFrame([{
            'hour': next_time.hour,
            'minute': next_time.minute,
            'dayofweek': next_time.dayofweek,
            'lag_1': current_lag_1,
            'lag_2': current_lag_2,
            'lag_3': current_lag_3
        }])
        pred_value = model.predict(features)[0]
        predictions.append({
            "time": next_time.isoformat(),
            "predicted_mem_util": float(pred_value)
        })
        current_lag_3 = current_lag_2
        current_lag_2 = current_lag_1
        current_lag_1 = pred_value
        current_time = next_time

    max_prediction = max(p['predicted_mem_util'] for p in predictions)
    final_prediction = predictions[-1]['predicted_mem_util']

    return {
        "device_mac": device_mac,
        "prediction_horizon_days": prediction_days,
        "total_steps_forecasted": steps_to_predict,
        "start_time": predictions[0]['time'],
        "end_time": predictions[-1]['time'],
        "max_predicted_util": max_prediction,
        "final_predicted_util": final_prediction,
        "forecast_series": predictions
    }