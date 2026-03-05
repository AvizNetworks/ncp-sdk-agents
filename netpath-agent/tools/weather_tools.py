"""Weather tools for netpath-agent."""

import random
from datetime import datetime, timedelta
from ncp import tool


@tool
def get_current_weather(location: str) -> dict:
    """Get current weather conditions for a location.

    Args:
        location: City name or location (e.g., "San Francisco", "London")

    Returns:
        Dictionary containing current weather information including
        temperature, condition, humidity, wind speed, and timestamp
    """
    # Mock weather conditions
    conditions = ["Sunny", "Partly Cloudy", "Cloudy", "Rainy", "Stormy", "Foggy", "Snowy"]

    # Generate mock data
    weather_data = {
        "location": location,
        "temperature": round(random.uniform(0, 35), 1),  # Celsius
        "temperature_fahrenheit": round(random.uniform(32, 95), 1),
        "condition": random.choice(conditions),
        "humidity": random.randint(30, 90),  # Percentage
        "wind_speed": round(random.uniform(0, 25), 1),  # km/h
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "feels_like": round(random.uniform(0, 35), 1)
    }

    return weather_data


@tool
def get_weather_forecast(location: str, days: int = 3) -> dict:
    """Get weather forecast for a location.

    Args:
        location: City name or location (e.g., "New York", "Tokyo")
        days: Number of days to forecast (1-7, default: 3)

    Returns:
        Dictionary containing forecast data with daily predictions
        including temperature ranges, conditions, and precipitation chance
    """
    if days < 1 or days > 7:
        days = 3  # Default to 3 days if invalid

    conditions = ["Sunny", "Partly Cloudy", "Cloudy", "Rainy", "Stormy"]
    forecast_days = []

    # Generate mock forecast for each day
    for i in range(days):
        forecast_date = datetime.now() + timedelta(days=i)
        day_forecast = {
            "date": forecast_date.strftime("%Y-%m-%d"),
            "day_of_week": forecast_date.strftime("%A"),
            "high_temp": round(random.uniform(15, 35), 1),  # Celsius
            "low_temp": round(random.uniform(5, 20), 1),
            "condition": random.choice(conditions),
            "precipitation_chance": random.randint(0, 100),  # Percentage
            "humidity": random.randint(40, 85)
        }
        forecast_days.append(day_forecast)

    forecast_data = {
        "location": location,
        "forecast_days": days,
        "forecast": forecast_days,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    return forecast_data
