import machine
from machine import RTC, Pin, PWM
from time import sleep
import ubinascii
import os
import time
import config

#########################################
# ESP-8266


class Pins:
    D0 = 16
    D1 = 5
    D2 = 4
    D3 = 0
    D4 = 2
    D5 = 14
    D6 = 12
    D7 = 13
    D8 = 15
    RX = 3
    TX = 1
    S2 = 9
    S3 = 10


def _pin(x):
    return getattr(Pins, x)


hour_format = 24
weekdays = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']


def connect():

    import network

    sta_if = network.WLAN(network.STA_IF)
    #ap_if = network.WLAN(network.AP_IF)

    print("sta_if.active()", sta_if.active())
    #print("ap_if.active()", ap_if.active())

    sta_if = network.WLAN(network.STA_IF)
    sta_if.active(True)
    #ap_if.active(False)
    if sta_if.isconnected():
        print("already connected")
    else:
        print("connecting...")
        print(config.SSID, config.PASS)
        result = sta_if.connect(config.SSID, config.PASS)
        print("result", result)
        x = 20
        while not sta_if.isconnected():
            x = x - 1
            print('.', x),
            if x == 0:
                print('giving up')
                return None
            sleep(.5)
    print('network config:', sta_if.ifconfig())

    # wlan=network.WLAN()
    mac = ubinascii.hexlify(network.WLAN().config('mac'), ':').decode().upper()
    # print(mac)
    return {'sta_if': sta_if, 'ip_address': list(sta_if.ifconfig()), 'mac_address': mac}


def sync_time():
    import ntptime
    import time

    ntptime.host = config.NTPTIME_HOST  # 'ca.pool.ntp.org'

    try:
        #print("Local time before synchronization：%s" % str(time.localtime()))
        # make sure to have internet connection
        ntptime.settime()
        #print("Local time after synchronization：%s" % str(time.localtime()))
    except:
        print("Error syncing time")


def get_current_time():
    tm = RTC().datetime()
    year = tm[0]
    month = tm[1]
    day = tm[2]
    weekday = tm[3]
    hour = tm[4]

    # Time of March change to DST
    daylight_start = time.mktime(
        (year, 3, (14-(int(5*year/4+1)) % 7), 1, 0, 0, 0, 0, 0))
    # Time of November change to EST
    daylight_end = time.mktime(
        (year, 11, (7-(int(5*year/4+1)) % 7), 1, 0, 0, 0, 0, 0))

    now = time.time()
    if now < daylight_start:  # we are before last sunday of march
        hr_offset = - 5  # EST: UTC-5H
    elif now < daylight_end:  # we are before last sunday of october
        hr_offset = - 4  # DST: UTC-4H
    else:  # we are after last sunday of october
        hr_offset = - 5  # EST: UTC-5H

    hour = hour + hr_offset
    if hour < 0:
        hour += 24  # + hour
    elif hour > 23:
        hour -= 24

    minute = tm[5]
    #seconds = tm[6]
    #ms = tm[7]

    return {
        'text': "{:02d}{:02d}".format(hour % hour_format, minute),
        'weekday': weekday
    }


def get_buzzer():
    buzzer = None
    if config.BUZZER:
        buzzer = PWM(Pin(_pin(config.BUZZER), Pin.OUT),
                     duty=0)
    return buzzer


def tm1637_clock_demo():
    import tm1637

    data = []

    tm = tm1637.TM1637(clk=Pin(_pin(config.TM1637_CLK)),
                       dio=Pin(_pin(config.TM1637_DIO)))

    # GRN  GRN BLACK
    # 3.3V VCC RED
    # D3   CLK WHITE
    # D4   DIO YELLOW

    h_sync = -1
    old_tm_str = ''
    button = Pin(_pin(config.BUTTON),
                 machine.Pin.IN, machine.Pin.PULL_UP)
    buzzer = get_buzzer()

    last_alarm = ''
    buzzer_count = 0

    while (True):
        a = button.value()

        if h_sync == -1 or (h != h_sync and h % 3 == 0):
            old_tm_str = 'sync'
            tm.show(old_tm_str, True)
            sync_time()
            tmp = get_data()
            if tmp != None:
                print(tmp)
                data = tmp
            h_sync = -1

        t = get_current_time()
        tm_str = t['text']
        #weekday = t['weekday']
        h = int(tm_str[0:2])
        if h_sync == -1:
            h_sync = h

        if tm_str != old_tm_str:
            tm.show(tm_str, True)
            old_tm_str = tm_str

        # if tm_str in data or f'{weekday}@{tm_str}' in data:
        if test_alarms(t, data):
            if tm_str != last_alarm:
                buzzer_count = 0
                last_alarm = tm_str

            if buzzer_count < config.BUZZS:
                freq_values = [400, 220, 330]
                freq = freq_values[buzzer_count]
                buzzer_count += 1
                sleep(1)
                # buzzer.value(1)
                print(f"ALARM !!!! ALARM !!!!  ALARM !!!! {buzzer_count}")
                if buzzer:
                    buzzer.freq(freq)
                    buzzer.duty(50)
                    sleep(config.DURATION)
                    buzzer.duty(0)

        if a:
            sleep(0.01)
            b = button.value()
        if a and not b:
            print('Button released!')
            #hour_format = 12 if hour_format - 12 else 24
            # print(hour_format)
            h_sync = -1


def is_workday(weekday):
    # 0 monday
    # 1 tuesday
    # 2 wednesday
    # 3 thursday
    # 4 friday
    # 5 saturday
    # 6 sunday
    return weekday < 5


def test_alarms(t, data):
    tm_str = t['text']
    weekday = t['weekday']
    weekday_str = weekdays[weekday]

    if is_workday(weekday) and f'workday@{tm_str}' in data:
        return True

    if not is_workday(weekday) and f'weekend@{tm_str}' in data:
        return True

    return tm_str in data or f'{weekday_str}@{tm_str}' in data


def get_data():
    data = []
    if config.META_URL:
        import urequests
        import json
        try:
            response = urequests.get(config.META_URL)
            data = json.loads(response.text)
            return [x.replace(':', '') for x in data]
        except:
            print(f'cannot fetch {config.META_URL}')
            return None
    return data


def main():
    get_buzzer()
    result = connect()
    if result:
        print(result)
        tm1637_clock_demo()


main()
