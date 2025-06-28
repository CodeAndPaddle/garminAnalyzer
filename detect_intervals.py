import numpy as np
import pandas as pd


def detect_speed_intervals(df, speed_column, threshold_acc=0.5, window_size=10):
    """
    Detect intervals of high-speed periods based on acceleration/deceleration patterns.

    Parameters:
    - df: DataFrame with speed and time data
    - speed_column: name of the speed column
    - threshold_acc: threshold for significant acceleration/deceleration
    - window_size: window size for smoothing noisy data

    Returns:
    - List of [start_idx, end_idx] intervals
    """
    speeds = df[speed_column].values
    avg_speed = np.mean(speeds)

    # Calculate acceleration using gradient
    acceleration = np.gradient(speeds)

    intervals = []
    start, end = -1, -1
    time = 0
    duration = len(df)

    while time < duration - window_size:
        # Calculate windowed averages to reduce noise
        window_speeds = speeds[time:time + window_size]
        window_acceleration = acceleration[time:time + window_size]

        avg_window_speed = np.mean(window_speeds)
        avg_window_acc = np.mean(window_acceleration)

        # Looking for start of interval (fast acceleration)
        if start == -1 and avg_window_acc > threshold_acc:
            # Find the first point in the window where acceleration becomes positive
            start_candidates = np.where(window_acceleration > 0)[0]
            if len(start_candidates) > 0:
                start = time + start_candidates[0]

        # If we have a start, look for end (fast deceleration)
        elif start != -1:
            # Check if we're still above average speed and look for deceleration
            if avg_window_speed > avg_speed and avg_window_acc < -threshold_acc:
                # Find the first point in the window where acceleration becomes negative
                end_candidates = np.where(window_acceleration < 0)[0]
                if len(end_candidates) > 0:
                    end = time + end_candidates[0]

                    # Validate interval: ensure speeds in interval are above average
                    interval_speeds = speeds[start:end + 1]
                    if np.mean(interval_speeds) > avg_speed:
                        intervals.append([start, end])

                    # Reset for next interval
                    start, end = -1, -1

            # Handle case where speed drops below average without strong deceleration
            elif avg_window_speed <= avg_speed:
                # End the interval here
                end = time
                interval_speeds = speeds[start:end + 1]
                if len(interval_speeds) > 0 and np.mean(interval_speeds) > avg_speed:
                    intervals.append([start, end])
                start, end = -1, -1

        time += 1

    # Handle case where interval extends to end of data
    if start != -1:
        end = duration - 1
        interval_speeds = speeds[start:end + 1]
        if np.mean(interval_speeds) > avg_speed:
            intervals.append([start, end])

    # Merge intervals less than 15 seconds
    def merge_close_intervals(intervals, min_gap=15):
        if not intervals:
            return []

        merged = [intervals[0]]

        for start, end in intervals[1:]:
            last_start, last_end = merged[-1]
            if start - last_end < min_gap:
                # Merge with the previous
                merged[-1] = [last_start, end]
            else:
                merged.append([start, end])

        return merged

    return merge_close_intervals(intervals)


