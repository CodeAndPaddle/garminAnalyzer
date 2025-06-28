import streamlit as st
import pandas as pd
import zipfile
import io
from garminconnect import Garmin
from fitparse import FitFile
from scipy.ndimage import uniform_filter1d
import detect_intervals
import altair as alt
from datetime import datetime, timedelta

# Constants
SPEED_THRESHOLD = 3
ENHANCED_SPEED = 'enhanced_speed'
MINIMUM_INTERVAL_HR = 140

# Initialize session state
if "login_failed" not in st.session_state:
    st.session_state.login_failed = False

def get_fit_files(client):
    activities = client.get_activities(0, 30)
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

def read_fit_to_df_from_data(fit_data):
    """Convert FIT data from memory buffer to DataFrame"""

    # Handle different data formats (requests response vs raw bytes)
    data = fit_data.content if hasattr(fit_data, 'content') else fit_data

    # Check if data is compressed (ZIP file)
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zip_file:
            fit_files = [name for name in zip_file.namelist() if name.endswith('.fit')]
            if fit_files:
                fit_data_bytes = zip_file.read(fit_files[0])
            else:
                fit_data_bytes = data
    except zipfile.BadZipFile:
        # Not a zip file, use data directly
        fit_data_bytes = data

    # Parse FIT file from memory
    fitfile = FitFile(io.BytesIO(fit_data_bytes))

    # Extract records
    records = []
    for record in fitfile.get_messages('record'):
        data_dict = {
            field.name: field.value
            for field in record
            if field.name in ("distance", "enhanced_speed", "heart_rate")
        }
        records.append(data_dict)

    # Convert to DataFrame
    df = pd.DataFrame(records)

    # Process enhanced_speed (convert m/s to km/h)
    if 'enhanced_speed' in df.columns:
        df["enhanced_speed"] = df["enhanced_speed"].astype(float) * 3.6
        df["enhanced_speed"] = df["enhanced_speed"].interpolate().bfill()
        df["enhanced_speed"] = uniform_filter1d(df["enhanced_speed"], size=7)

    # Process heart_rate
    if 'heart_rate' in df.columns:
        df["heart_rate"] = df["heart_rate"].interpolate()

    return df

def summarize_intervals(intervals, df):
    summary = []

    for i, (left, right) in enumerate(intervals):
        min = (right - left) // 60
        sec = (right - left) %60
        # Add the interval
        summary.append({
            "Type": f"Interval : {i+1}",
            "duration [min]": f"{min:02d}:{sec:02d}",
            "avg speed [kmh]": f"{round(df.loc[left:right, "enhanced_speed"].mean(), 2):.2f}",
            "distance [m]": round(df.loc[right, "distance"] - df.loc[left, "distance"]),
            "avg heart_rate [bpm]": round(df.loc[left:right, "heart_rate"].mean())
        })

        # Add recovery period (if not the last interval)
        if i < len(intervals) - 1:
            recovery_start = right
            recovery_end = intervals[i + 1][0]

            if recovery_start < recovery_end:  # Valid recovery period
                summary.append({
                    "Type": "Recovery",
                    "duration [min]": f"{(recovery_end-recovery_start)//60:02d}:{(recovery_end-recovery_start)%60:02d}",
                    "avg speed [kmh]": f"{round(df.loc[recovery_start:recovery_end, "enhanced_speed"].mean(), 2):.2f}",
                    "distance [m]": round(df.loc[recovery_end, "distance"] - df.loc[recovery_start, "distance"]),
                    "avg heart_rate [bpm]": round(df.loc[recovery_start:recovery_end, "heart_rate"].mean())
                })

    return summary

# ========== Streamlit App ==========

st.title("Garmin Interval Analyzer")
st.write("Login to Garmin and choose an activity from the last 7 days to analyze.")

# Initialize session state
if 'client' not in st.session_state:
    st.session_state.client = None
if 'activities' not in st.session_state:
    st.session_state.activities = None
if 'login_failed' not in st.session_state:
    st.session_state.login_failed = False

# Step 1: Login Form
if st.session_state.client is None:
    with st.form("login_form"):
        email = st.text_input("Garmin Email")
        password = st.text_input("Garmin Password", type="password")
        submit = st.form_submit_button("Login to Garmin")

        if st.session_state.login_failed:
            st.error("Login failed. Please check your email and password.")

    if submit:
        try:
            with st.spinner("Logging into Garmin..."):
                client = Garmin(email, password)
                client.login()

                end_date = datetime.now()
                start_date = end_date - timedelta(days=7)

                activities = client.get_activities_by_date(
                    start_date.strftime('%Y-%m-%d'),
                    end_date.strftime('%Y-%m-%d')
                )

                # Store in session state
                st.session_state.client = client
                st.session_state.activities = activities
                st.session_state.login_failed = False
                st.rerun()  # Refresh to show next step

        except Exception as e:
            st.session_state.login_failed = True
            st.error("Login failed. Please check your Garmin email and password.")

# Step 2: Activity Selection
elif st.session_state.activities is not None and len(st.session_state.activities) > 0:
    st.success("✅ Logged in successfully!")
    st.subheader("Select an Activity from the Last Week")

    # Create a nice display of activities
    activity_options = []
    for i, activity in enumerate(st.session_state.activities):
        activity_name = activity.get('activityName', 'Unnamed Activity')
        activity_type = activity.get('activityType', {}).get('typeKey', 'unknown')
        start_time = activity.get('startTimeLocal', '')
        duration = activity.get('duration', 0)
        distance = activity.get('distance', 0)

        # Format duration (convert from seconds)
        duration_min = int(duration / 60) if duration else 0
        duration_sec = duration - (duration_min * 60)
        distance_km = round(distance / 1000, 2) if distance else 0

        display_text = f"{activity_name} ({activity_type}) - {start_time[:10]} - {duration_min}min:{duration_sec}sec - {distance_km}km"
        activity_options.append((display_text, i))

    # Activity selection
    selected_display = st.selectbox(
        "Choose an activity:",
        options=[opt[0] for opt in activity_options],
        format_func=lambda x: x
    )

    # Get the selected activity index
    selected_index = next(i for display, i in activity_options if display == selected_display)
    selected_activity = st.session_state.activities[selected_index]

    # Show activity details
    with st.expander("Activity Details"):
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**Activity:** {selected_activity.get('activityName', 'N/A')}")
            st.write(f"**Type:** {selected_activity.get('activityType', {}).get('typeKey', 'N/A')}")
            st.write(f"**Date:** {selected_activity.get('startTimeLocal', 'N/A')[:10]}")
        with col2:
            duration_min = int(selected_activity.get('duration', 0) / 60)
            distance_km = round(selected_activity.get('distance', 0) / 1000, 2)
            st.write(f"**Duration:** {duration_min} minutes")
            st.write(f"**Distance:** {distance_km} km")

    # Analyze button
    if st.button("🔍 Analyze This Activity", type="primary"):
        try:
            activity_id = selected_activity['activityId']

            with st.spinner("Downloading and analyzing activity data..."):
                # Download FIT data directly to memory
                fit_data = st.session_state.client.download_activity(
                    activity_id,
                    dl_fmt=st.session_state.client.ActivityDownloadFormat.ORIGINAL
                )

                # Convert to DataFrame
                df = read_fit_to_df_from_data(fit_data)

            st.success("Activity data loaded!")

            # Building the chart
            intervals = detect_intervals.detect_speed_intervals(df, ENHANCED_SPEED, 0.5, 10)
            chart_df = df.reset_index().melt(
                id_vars="index",
                value_vars=["enhanced_speed", "heart_rate"],
                var_name="Metric",
                value_name="Value"
            )
            # Create DataFrame of intervals
            interval_df = pd.DataFrame(intervals, columns=["start", "end"])

            # Build yellow rectangles
            interval_layer = alt.Chart(interval_df).mark_rect(opacity=0.5, color="yellow").encode(
                x="start:Q",
                x2="end:Q"
            )

            color_map = alt.Scale(domain=["enhanced_speed", "heart_rate"], range=["blue", "red"])
            chart = alt.Chart(chart_df).mark_line().encode(
                x=alt.X('index', title='Time [s]'),
                y='Value',
                color=alt.Color('Metric', scale=color_map)
            ).properties(height=300)

            # Combine the chart with intervals
            final_chart = interval_layer + chart
            st.altair_chart(final_chart, use_container_width=True)

            st.info("Detecting intervals...")

            summary = summarize_intervals(intervals, df)

            st.subheader("Detected Intervals")
            summary_df = pd.DataFrame(summary)
            st.dataframe(summary_df.style.hide(axis='index'), use_container_width=True)

        except Exception as e:
            st.error(f"Error analyzing activity: {str(e)}")

    # Logout option
    if st.button("🔓 Logout"):
        st.session_state.client = None
        st.session_state.activities = None
        st.session_state.login_failed = False
        st.rerun()

# Step 3: No activities found
elif st.session_state.activities is not None and len(st.session_state.activities) == 0:
    st.warning("No activities found in the last week.")
    if st.button("🔓 Logout"):
        st.session_state.client = None
        st.session_state.activities = None
        st.session_state.login_failed = False
        st.rerun()

