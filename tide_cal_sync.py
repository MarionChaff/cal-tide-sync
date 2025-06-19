# Imports

import numpy as np
import datetime as dt
import sys

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


# Scrapes tides from SHOM

def scrape_tides(start_date, num_days=10, harbor='SAINT-MALO'):

    slack_tides = []

    driver = webdriver.Chrome()

    for day in range(0, num_days):

        try:

            date_obj = start_date + dt.timedelta(days=day)
            url = f'https://maree.shom.fr/harbor/{harbor}/hlt/0?date={date_obj.year}-{date_obj.month}-{date_obj.day}&utc=standard'
            driver.get(url)
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, '//table//tbody/tr[2]/td[2]')))

            for tide in range(2, 6):
                x_path_hour = f'//*[@id="ember657"]/div/table/tbody/tr[{tide}]/td[2]'
                tide_hour = driver.find_element(By.XPATH, x_path_hour).text

                if tide_hour != '--:--':
                    time_obj = dt.datetime.strptime(tide_hour, '%H:%M').time()
                    combined_datetime = dt.datetime.combine(date_obj, time_obj)

                    x_path_level = f'//*[@id="ember657"]/div/table/tbody/tr[{tide}]/td[3]'
                    tide_level = float(driver.find_element(By.XPATH, x_path_level).text)

                    x_path_coeff = f'//*[@id="ember657"]/div/table/tbody/tr[{tide}]/td[4]'
                    try:
                        tide_coeff = int(driver.find_element(By.XPATH, x_path_coeff).text)
                    except Exception:
                        tide_coeff = None

                    slack_tides.append((combined_datetime, tide_level, tide_coeff))

        except Exception:
            continue

    return slack_tides


# Derives full tide curve

def create_tide_curve(slack_tides):

    coeff = None
    coeff_list = []
    tide_x = []
    tide_y = []

    for k in range(0,len(slack_tides)-1):

        start_timestamp = slack_tides[k][0].timestamp()
        end_timestamp = slack_tides[k+1][0].timestamp()

        start_tide_level = slack_tides[k][1]
        end_tide_level = slack_tides[k+1][1]

        try:
            coeff = int(slack_tides[k][2])
        except Exception:
            None

        x_values = np.arange(start_timestamp, end_timestamp, 60)
        x_values_datetime = [dt.datetime.fromtimestamp(ts) for ts in x_values]

        amplitude = (end_tide_level - start_tide_level) / 2
        frequency = np.pi / (start_timestamp - end_timestamp)

        y_values = start_tide_level + amplitude * (1 + np.sin(frequency * (x_values - start_timestamp) - np.pi / 2))

        tide_x.extend(x_values_datetime[:-1])
        tide_y.extend(y_values[:-1])
        coeff_list.extend([coeff] * (len(x_values)-1))

    full_tides = list(zip(tide_x, tide_y, coeff_list))

    return full_tides


# Derives relevant tide slots from full tides

def create_tide_slots (full_tides, surf_thresholds = (7.5, 10.8)):

    intervals = []
    in_interval = False

    for date, tide, coeff in full_tides:
        if surf_thresholds[0] < tide < surf_thresholds[1]:
            if not in_interval:
                start_date = date
                in_interval = True
        else:
            if in_interval:
                comment =f'Coeff. {coeff}'
                intervals.append((start_date, date, comment))
                in_interval = False

    return intervals


# Creates Google events

def create_google_event(event_item, service, calendar_id):

    event = {
        'summary': f'Tide window, {event_item[2]}',
        'start': {
            'dateTime': event_item[0].strftime('%Y-%m-%dT%H:%M:%S'),
            'timeZone': 'Europe/Paris',
        },
        'end': {
            'dateTime': event_item[1].strftime('%Y-%m-%dT%H:%M:%S'),
            'timeZone': 'Europe/Paris',
        },
        'colorId': '7'}

    event = service.events().insert(calendarId=calendar_id, body=event).execute()

    print(f"Event @ {event_item[0].strftime('%Y-%m-%dT%H:%M')} successfully created")

    return None

def post_google_event(event_slots, calendar_id):

    scopes = ["https://www.googleapis.com/auth/calendar"]
    flow = InstalledAppFlow.from_client_secrets_file("credentials.json", scopes)
    creds = flow.run_local_server(port=0)
    service = build("calendar", "v3", credentials=creds)

    for event in event_slots:
        create_google_event(event, service, calendar_id)

    return None


def main(start_date, calendar_id):

    start_date = dt.datetime.strptime(start_date, '%d/%m/%y')
    num_days=10

    slack_tides = scrape_tides(start_date, num_days=num_days)
    full_tides = create_tide_curve(slack_tides)
    event_slots = create_tide_slots(full_tides)
    post_google_event(event_slots, calendar_id)

    return None


if __name__ == "__main__":
    calendar_id = '2a075d8844c44bce6e2573676a195b31626de6e32649d7d93d0b5b06ddbdee1a@group.calendar.google.com'
    input_date = sys.argv[1]
    main(input_date, calendar_id)
