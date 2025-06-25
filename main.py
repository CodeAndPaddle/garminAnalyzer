import pandas as pd
import zipfile
import io
from garminconnect import Garmin
from fitparse import FitFile
import numpy as np
from scipy.signal import find_peaks
from scipy.ndimage import uniform_filter1d



# This is a sample Python script.

# Press ⌃R to execute it or replace it with your code.
# Press Double ⇧ to search everywhere for classes, files, tool windows, actions, and settings.


def print_hi(name):
    # Use a breakpoint in the code line below to debug your script.
    print(f'{name}')  # Press ⌘F8 to toggle the breakpoint.

def get_activity_from_garmin_connect() -> str:
    print(f'get_activity_from_garmin_connect()')
    # Garmin login details
    email = input('Enter your Garmin Email Address: ') or "benjano9397@gmail.com"
    password = input('Enter your Garmin Password: ') or "Ronb1997"

    # Login
    client = Garmin(email, password)
    client.login()

    # Get activities
    activities = client.get_activities(0, 1)  # latest activity
    activityID = activities[0]['activityId']

    # Download .fit file
    fit_file = client.download_activity(activityID, dl_fmt=client.ActivityDownloadFormat.ORIGINAL)

    # Extract content if it's a response object
    if hasattr(fit_file, 'content'):
        data = fit_file.content
    else:
        data = fit_file

    # Check if it's a ZIP file
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zip_file:
            # Get the first .fit file from the ZIP
            fit_files = [name for name in zip_file.namelist() if name.endswith('.fit')]
            if fit_files:
                fit_data = zip_file.read(fit_files[0])
            else:
                fit_data = data
    except zipfile.BadZipFile:
        # Not a ZIP file, use as-is
        fit_data = data

    # Save to disk
    with open(f"{activityID}.fit", "wb") as f:
        f.write(fit_data)

    print(f"Saved as {activityID}.fit")

    return activityID

def read_fit_to_df(activity_id) -> pd.DataFrame:
    print(f'read_fit_to_df')
    fitfile = FitFile(f"{activity_id}.fit")

    # Extract records (one data point per time step)
    records = []
    for record in fitfile.get_messages('record'):
        data = {}
        for field in record:
            if field.name in ("distance","enhanced_speed","heart_rate"):
                data[field.name] = field.value
        records.append(data)

    if not records:
        print("No 'record' messages — try 'session' or 'lap' instead!")

    # Convert to DataFrame
    df = pd.DataFrame(records)
    df["enhanced_speed"] = df["enhanced_speed"].values * 3.6 #kmh
    #df["enhanced_speed"] = uniform_filter1d(df["enhanced_speed"], size = 3) #smoothing

    # Preview (debugging)
    #print(df)

    return df

def detect_intervals(df) :
    print(f'detect_intervals(df)')
    intervals= []
    duration = len(df)
    index = 0
    in_interval = False
    start_interval = 0

    while index < duration-10 : # the threshold is defined to be speed[time+10]-time > 5 & speed[[time+10] > 12kmh
        current_speed = df["enhanced_speed"].iloc[index]
        future_speed = df["enhanced_speed"].iloc[index + 10]
        #print(f"{index}: current={current_speed:.2f}, future={future_speed:.2f}")

        if not in_interval :
            # start_interval
            if (future_speed - current_speed) > 5 and future_speed > 11:
                start_interval = index + 5 # the middle is set to be the start
                in_interval = True
        else:
            if index+10 == duration:
                end_interval = duration
                intervals.append((start_interval, end_interval))

            if (current_speed - future_speed ) > 5 and future_speed < 11:
                end_interval = index + 5  # the middle is set to be the end
                in_interval = False
                intervals.append((start_interval, end_interval))
        index += 1
    print(f"{intervals} detect_intervals")
    return intervals

def summarize_intervals(intervals,df):
    print(f'summarize_intervals')
    intervals_summary=[]
    for interval in intervals:
        interval_summary = {"duration [min]": round((interval[1] - interval[0])/60),
                            "avg speed [kmh]": round(float(df.loc[interval[0]:interval[1], "enhanced_speed"].mean()),2),
                            "avg heart_rate [bpm]": round(float(df.loc[interval[0]:interval[1], "heart_rate"].mean())),
                            "distance [m]": round(float(df.loc[interval[1], "distance"] - df.loc[interval[0], "distance"]))}
        intervals_summary.append(interval_summary)
    return intervals_summary

def plot_intervals(intervals_summary):
    print(f'plot_intervals(intervals_summary){len(intervals_summary)}')
    df = pd.DataFrame(intervals_summary)
    df.insert(0, "interval", range(1, len(df) + 1))
    print(df)

def detect_intervals_improved(df, min_interval_duration=30, min_recovery_duration=15,
                              speed_threshold=11, adaptive_threshold=True):
    """
    Improved interval detection that handles cases where recovery speed doesn't drop dramatically.

    Parameters:
    - df: DataFrame with 'enhanced_speed' column
    - min_interval_duration: Minimum duration for an interval (seconds)
    - min_recovery_duration: Minimum duration for recovery between intervals (seconds)
    - speed_threshold: Minimum speed to consider as "high intensity" (km/h)
    - adaptive_threshold: Whether to use adaptive thresholds based on data
    """
    print(f'detect_intervals_improved(df)')

    # Convert rfrspeed to km/h ansdcsdcd smooth the data
    speed_kmh = df["enhanced_speed"].values
    smoothed_speed = uniform_filter1d(speed_kmh, size=5)  # 5-point moving average

    # Calculate speed derivatives for better transition detection
    speed_gradient = np.gradient(smoothed_speed)
dddddd
    # Adaptive thresholds based on data characteristics
    if adaptive_threshold:
        speed_mean = np.mean(smoothed_speed)
        speed_std = np.std(smoothed_speed)
        high_speed_threshold = max(speed_threshold, speed_mean + 0.5 * speed_std)
        low_speed_threshold = speed_mean - 0.3 * speed_std
        acceleration_threshold = 0.3 * speed_std  # Adaptive acceleration threshold
    else:
        high_speed_threshold = speed_threshold
        low_speed_threshold = speed_threshold * 0.7
        acceleration_threshold = 2.0

    intervals = []
    duration = len(df)

    # Method 1: Peak-based detection for clear intervals
    peaks, _ = find_peaks(smoothed_speed, height=high_speed_threshold, distance=min_interval_duration)

    if len(peaks) > 0:
        intervals_from_peaks = extract_intervals_from_peaks(
            smoothed_speed, speed_gradient, peaks,
            high_speed_threshold, low_speed_threshold,
            min_interval_duration, min_recovery_duration
        )
        intervals.extend(intervals_from_peaks)

    # Method 2: State machine approach for gradual transitions
    if len(intervals) == 0 or should_use_state_machine(smoothed_speed, intervals):
        intervals_from_state = state_machine_detection(
            smoothed_speed, speed_gradient,
            high_speed_threshold, low_speed_threshold, acceleration_threshold,
            min_interval_duration, min_recovery_duration
        )
        intervals = merge_overlapping_intervals(intervals + intervals_from_state)

    # Method 3: Relative intensity detection (fallback)
    if len(intervals) == 0:
        intervals = relative_intensity_detection(
            smoothed_speed, min_interval_duration, min_recovery_duration
        )

    # Post-process intervals
    intervals = filter_short_intervals(intervals, min_interval_duration)
    intervals = merge_close_intervals(intervals, min_recovery_duration)

    print(f"Detected {len(intervals)} intervals: {intervals}")
    return intervals


def extract_intervals_from_peaks(speed, gradient, peaks, high_thresh, low_thresh,
                                 min_interval_dur, min_recovery_dur):
    """Extract intervals around detected peaks"""
    intervals = []

    for peak in peaks:
        # Find interval start (look backwards for acceleration)
        start = peak
        for i in range(peak, max(0, peak - 60), -1):  # Look back up to 60 seconds
            if speed[i] < low_thresh or (i > 0 and gradient[i] < -0.5):
                start = i
                break

        # Find interval end (look forwards for deceleration)
        end = peak
        for i in range(peak, min(len(speed), peak + 60)):  # Look forward up to 60 seconds
            if speed[i] < low_thresh or gradient[i] < -0.5:
                end = i
                break

        if end - start >= min_interval_dur:
            intervals.append((start, end))

    return intervals


def state_machine_detection(speed, gradient, high_thresh, low_thresh, accel_thresh,
                            min_interval_dur, min_recovery_dur):
    """State machine approach for detecting intervals with gradual transitions"""
    intervals = []
    state = "recovery"  # "recovery", "building", "interval", "declining"
    interval_start = 0
    last_transition = 0

    for i in range(1, len(speed)):
        current_speed = speed[i]
        accel = gradient[i]

        if state == "recovery":
            # Look for start of build-up
            if accel > accel_thresh and current_speed > low_thresh:
                state = "building"
                potential_start = i

        elif state == "building":
            # Confirm we're in an interval
            if current_speed > high_thresh:
                state = "interval"
                interval_start = potential_start
            elif accel < -accel_thresh:  # False start
                state = "recovery"

        elif state == "interval":
            # Look for end conditions
            time_in_interval = i - interval_start

            # End if speed drops significantly OR we've been at high intensity long enough
            # and see signs of recovery
            if (current_speed < low_thresh or
                    (time_in_interval > min_interval_dur and accel < -accel_thresh / 2)):

                if time_in_interval >= min_interval_dur:
                    intervals.append((interval_start, i))

                state = "recovery"
                last_transition = i

    return intervals


def relative_intensity_detection(speed, min_interval_dur, min_recovery_dur):
    """Fallback method using relative intensity zones"""
    # Define intensity zones based on percentiles
    p90 = np.percentile(speed, 90)
    p70 = np.percentile(speed, 70)
    p50 = np.percentile(speed, 50)

    # Find periods above 70th percentile
    high_intensity = speed > p70

    intervals = []
    in_interval = False
    start = 0

    for i, is_high in enumerate(high_intensity):
        if not in_interval and is_high:
            start = i
            in_interval = True
        elif in_interval and not is_high:
            if i - start >= min_interval_dur:
                intervals.append((start, i))
            in_interval = False

    # Handle case where session ends during interval
    if in_interval and len(speed) - start >= min_interval_dur:
        intervals.append((start, len(speed)))

    return intervals


def should_use_state_machine(speed, existing_intervals):
    """Determine if state machine detection should be used"""
    # Use state machine if no clear peaks found or if speed variation is low
    speed_cv = np.std(speed) / np.mean(speed)  # Coefficient of variation
    return len(existing_intervals) == 0 or speed_cv < 0.3


def merge_overlapping_intervals(intervals):
    """Merge overlapping intervals"""
    if not intervals:
        return []

    intervals.sort()
    merged = [intervals[0]]

    for current in intervals[1:]:
        last = merged[-1]
        if current[0] <= last[1]:  # Overlapping
            merged[-1] = (last[0], max(last[1], current[1]))
        else:
            merged.append(current)

    return merged


def merge_close_intervals(intervals, min_gap):
    """Merge intervals that are too close together"""
    if len(intervals) < 2:
        return intervals

    merged = [intervals[0]]

    for current in intervals[1:]:
        last = merged[-1]
        if current[0] - last[1] < min_gap:  # Too close
            merged[-1] = (last[0], current[1])
        else:
            merged.append(current)

    return merged


def filter_short_intervals(intervals, min_duration):
    """Remove intervals shorter than minimum duration"""
    return [(start, end) for start, end in intervals if end - start >= min_duration]


# Enhanced version of your original algorithm with improvements
def detect_intervals_enhanced_original(df, lookforward=10, speed_increase_thresh=3,
                                       speed_decrease_thresh=3, min_speed_thresh=11,
                                       time_based_recovery=True):
    """
    Enhanced version of your original algorithm with better recovery detection
    """
    print(f'detect_intervals_enhanced_original(df)')
    intervals = []
    duration = len(df)
    index = 0
    in_interval = False
    start_interval = 0
    time_in_recovery = 0
    max_recovery_time = 30  # Maximum time to wait for speed drop during recovery

    # Convert to km/h and smooth
    speed_kmh = df["enhanced_speed"].values * 3.6
    smoothed_speed = uniform_filter1d(speed_kmh, size=3)

    while index < duration - lookforward:
        current_speed = smoothed_speed[index]
        future_speed = smoothed_speed[index + lookforward]

        # Calculate recent average for more stable recovery detection
        if index >= 5:
            recent_avg_speed = np.mean(smoothed_speed[index - 5:index + 1])
        else:
            recent_avg_speed = current_speed

        if not in_interval:
            # Start interval detection
            if (future_speed - current_speed) > speed_increase_thresh and future_speed > min_speed_thresh:
                start_interval = index + lookforward // 2
                in_interval = True
                time_in_recovery = 0
        else:
            # End interval detection with multiple criteria

            # Criteria 1: Traditional speed drop
            speed_dropped = (current_speed - future_speed) > speed_decrease_thresh and future_speed < min_speed_thresh

            # Criteria 2: Time-based recovery (sustained lower intensity)
            if time_based_recovery:
                if recent_avg_speed < min_speed_thresh * 0.8:  # 80% of threshold
                    time_in_recovery += 1
                else:
                    time_in_recovery = 0

                time_based_end = time_in_recovery > max_recovery_time
            else:
                time_based_end = False

            # Criteria 3: Relative speed drop (even if not below absolute threshold)
            relative_drop = current_speed > min_speed_thresh and (
                        current_speed - future_speed) > speed_decrease_thresh * 0.7

            # End interval if any criteria met
            if speed_dropped or time_based_end or relative_drop:
                end_interval = index + lookforward // 2
                intervals.append((start_interval, end_interval))
                in_interval = False
                time_in_recovery = 0

            # Handle end of data
            if index + lookforward >= duration - 1:
                end_interval = duration - 1
                intervals.append((start_interval, end_interval))

        index += 1

    print(f"{intervals} detect_intervals_enhanced")
    return intervals
# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    print_hi('Start Application')
    #Activity_ID = get_activity_from_garmin_connect()
    #Data_frame = read_fit_to_df(Activity_ID)
    Data_frame = read_fit_to_df("19497947581")
    Intervals = detect_intervals(Data_frame)
    Intervals_summary = summarize_intervals(Intervals,Data_frame)
    plot_intervals(Intervals_summary)













