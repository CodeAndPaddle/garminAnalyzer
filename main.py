from garminconnect import Garmin
import datetime

# This is a sample Python script.

# Press ⌃R to execute it or replace it with your code.
# Press Double ⇧ to search everywhere for classes, files, tool windows, actions, and settings.


def print_hi(name):
    # Use a breakpoint in the code line below to debug your script.
    print(f'hHi, {name}')  # Press ⌘F8 to toggle the breakpoint.

def fetch_activity_from_garmin():
    # 1) Your Garmin login
    email = input('Enter your Garmin Email Address: ')
    password = input('Enter your Garmin Password: ')

    # 2) Login
    client = Garmin(email, password)
    client.login()

    # 3) Get activities
    activities = client.get_activities(0, 1)  # latest activity

    # 4) Get the activity ID
    activity_id = activities[0]['activityId']

    # 5) Download .fit file
    fit_file = client.download_activity(activity_id, dl_fmt=client.ActivityDownloadFormat.ORIGINAL)

    # 6) Save to disk
    with open(f"{activity_id}.fit", "wb") as f:
        f.write(fit_file)

    print(f"Saved as {activity_id}.fit")



# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    print_hi('PyCharm')

# See PyCharm help at https://www.jetbrains.com/help/pycharm/


# import the last fit file from garmin connect and export is as csv file
from garminconnect import Garmin
import datetime

