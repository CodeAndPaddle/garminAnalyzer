import streamlit as st
import pandas as pd
import zipfile
import io
from garminconnect import Garmin
from fitparse import FitFile
from scipy.ndimage import uniform_filter1d
import detect_intervals

# Constants
SPEED_THRESHOLD = 3
ENHANCED_SPEED = 'enhanced_speed'
MINIMUM_INTERVAL_HR = 150

def get_fit_file(email, password):
    try:
        client = Garmin(email, password)
        client.login()
    except Exception as e:
        st.error("Login failed. Please check your Garmin email and password.")
        st.stop()

    activities = client.get_activities(0, 1)
    activityID = activities[0]['activityId']
    fit_file = client.download_activity(activityID, dl_fmt=client.ActivityDownloadFormat.ORIGINAL)
    data = fit_file.content if hasattr(fit_file, 'content') else fit_file

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zip_file:
            fit_files = [name for name in zip_file.namelist() if name.endswith('.fit')]
            fit_data = zip_file.read(fit_files[0]) if fit_files else data
    except zipfile.BadZipFile:
        fit_data = data

    with open(f"{activityID}.fit", "wb") as f:
        f.write(fit_data)

    return activityID

def read_fit_to_df(activity_id):
    fitfile = FitFile(f"{activity_id}.fit")
    records = []
    for record in fitfile.get_messages('record'):
        data = {field.name: field.value for field in record if field.name in ("distance", "enhanced_speed", "heart_rate")}
        records.append(data)

    df = pd.DataFrame(records)
    df["enhanced_speed"] = df["enhanced_speed"].astype(float) * 3.6
    df["enhanced_speed"] = df["enhanced_speed"].interpolate()
    df["enhanced_speed"] = uniform_filter1d(df["enhanced_speed"], size=5)
    df["heart_rate"] = df["heart_rate"].interpolate()
    return df

def summarize_intervals(intervals, df):
    summary = []
    for left, right in intervals:
        summary.append({
            "duration [min]": round((right - left) / 60),
            "avg speed [kmh]": round(df.loc[left:right, "enhanced_speed"].mean(), 2),
            "avg heart_rate [bpm]": round(df.loc[left:right, "heart_rate"].mean()),
            "distance [m]": round(df.loc[right, "distance"] - df.loc[left, "distance"])
        })
    return summary

# ========== Streamlit App ==========

st.title("Garmin Interval Analyzer")
st.write("Login to Garmin and get interval analysis of your latest activity.")

with st.form("login_form"):
    email = st.text_input("Garmin Email")
    password = st.text_input("Garmin Password", type="password")
    submit = st.form_submit_button("Analyze My Activity")
    if st.session_state.login_failed:
        st.error("Login failed. Please check your email and password.")
if submit:
    try:
        st.info("Logging into Garmin and downloading your latest activity...")
        activity_id = get_fit_file(email, password)
        df = read_fit_to_df(activity_id)

        st.success("Activity data loaded!")

        st.line_chart(df[["enhanced_speed", "heart_rate"]])

        st.info("Detecting intervals...")
        intervals = detect_intervals.detect_speed_intervals(df, ENHANCED_SPEED, 0.5, 10)
        summary = summarize_intervals(intervals, df)

        st.subheader("Detected Intervals")
        summary_df = pd.DataFrame(summary)
        summary_df.index += 1
        st.dataframe(summary_df)

        st.subheader("High HR Intervals")
        st.dataframe(summary_df[summary_df["avg heart_rate [bpm]"] > MINIMUM_INTERVAL_HR])

    except Exception as e:
        st.error(f"Something went wrong: {e}")