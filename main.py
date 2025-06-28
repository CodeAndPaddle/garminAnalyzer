import pandas as pd
import zipfile
import io
from garminconnect import Garmin
from fitparse import FitFile
from scipy.ndimage import uniform_filter1d
import detect_intervals

#consnt
SPEED_THRESHOLD = 3
ENHANCED_SPEED = 'enhanced_speed'
MINIMUM_INTERVAL_LENGTH = 60
MINIMUM_INTERVAL_SPEED = 12.5
MINIMUM_INTERVAL_HR = 140

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
    df["enhanced_speed"] = df["enhanced_speed"].astype(float) * 3.6 #kmh
    df["enhanced_speed"] = df["enhanced_speed"].interpolate()
    df["enhanced_speed"] = uniform_filter1d(df["enhanced_speed"], size = 5) #smoothing
    df["heart_rate"] = df["heart_rate"].interpolate()

    # Preview (debugging)
    #print(df)

    return df

def summarize_intervals(intervals,df):
    print(f'summarize_intervals')
    intervals_summary=[]
    for interval in intervals:
        left , right = interval
        print(f"left: {left}, right: {right}, slice length: {len(df.loc[left:right])}")
        interval_summary = {"duration [min]": round((right - left)/60),
                            "avg speed [kmh]": round(float(df.loc[left:right, "enhanced_speed"].mean()),2),
                            "avg heart_rate [bpm]": round(float(df.loc[left:right, "heart_rate"].mean())),
                            "distance [m]": round(float(df.loc[right, "distance"] - df.loc[left, "distance"]))}
        intervals_summary.append(interval_summary)
    return intervals_summary

def plot_intervals(intervals_summary):
    print(f'plot_intervals(intervals_summary){len(intervals_summary)}')
    df = pd.DataFrame(intervals_summary)
    df.insert(0, "interval", range(1, len(df) + 1))
    print(df[df["avg heart_rate [bpm]"] > MINIMUM_INTERVAL_HR])


if __name__ == '__main__':
    print_hi('Start Application')
    Activity_ID = get_activity_from_garmin_connect()
    Data_frame = read_fit_to_df(Activity_ID)
    Intervals = detect_intervals.detect_speed_intervals(Data_frame,ENHANCED_SPEED,0.5,10)
    print(Intervals)
    Intervals_summary = summarize_intervals(Intervals,Data_frame)
    plot_intervals(Intervals_summary)













