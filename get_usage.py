import requests
import json
import time
import yaml
from threading import Thread
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from datetime import datetime, date

log_file = 'usage.log'

#function to write the output to file
def log_usage(location, message):
    file = open(location, 'a')
    file.write(message+"\n")
    file.close

#function to send the output to slack
def send_alert_slack(webhook, data, pct_alert=10, days_alert=7):
    message = ""
    
    if int(data['Error_code']) != 0 or int(data['Remaining pct'].split("%")[0]) < pct_alert or int(data['Remaining Days']) < days_alert:
        for key in data:
            message += (key+": "+data[key]+"\n")
        slack_data = {'text': message}
        requests.post(webhook, data=json.dumps(slack_data), headers={'Content-Type': 'application/json'})
        

#fubnction to access vodafone.com.eg website and scrap the data needed 
def get_voda_usage(username, password, isVerbose=True, logFile=log_file, isAlert=False, slackWebhook="", MBAlert=10, daysAlert=7 ):
    try:
        options = Options()
        options.add_argument('--headless=new')
        options.add_experimental_option('excludeSwitches', ['enable-logging'])


        driver = webdriver.Chrome(options=options)
        driver.get('https://web.vodafone.com.eg/spa/redHome')
        driver.get(driver.current_url)
        time.sleep(4)
        usernameElement = driver.find_element(By.ID, 'username')
        usernameElement.send_keys(username)
        passwordElement = driver.find_element(By.ID, 'password')
        passwordElement.send_keys(password)
        time.sleep(4)
        btnElement = driver.find_element(By.ID, 'submitBtn')
        btnElement.click()
        time.sleep(4)
        totalMB = int(driver.find_element(By.ID, 'txt-total-').text.replace(',',''))
        remainingMB = int(driver.find_element(By.ID, 'txt-remaining-').text.replace(',',''))
        remainingDays = driver.find_element(By.CLASS_NAME, 'card-body-subtitle.mt-2').text.split(' ')[0]
        response = {
                'Timestamp' : datetime.now().strftime("%d-%m-%Y %H:%M:%S"),
                'MSISDN' : username,
                'Error_code': "0",
                'Total MBs' : str(totalMB),
                'Remaining MBs' : str(remainingMB),
                'Remaining pct' : str(round((remainingMB*100)/totalMB))+"%",
                'Remaining Days' : remainingDays
                }
        driver.quit()
    except Exception as error_message:
        response = {
                    'Timestamp' : datetime.now().strftime("%d-%m-%Y %H:%M:%S"),
                    'MSISDN' : username,
                    'Error_code': "500",
                    'Response'  : error_message
                }
    if isVerbose:            
        log_usage(logFile, str(response))
    if isAlert:
        send_alert_slack(slackWebhook, response, MBAlert, daysAlert)
    print(response)



# function to handle te.eg response codes
def handle_we_response(action, url, headers={}, payload={}, username=""):
    response = requests.request(action, url, headers=headers, data=json.dumps(payload))
    if response.ok:
        response_json = {
                'Timestamp' : datetime.now().strftime("%d-%m-%Y %H:%M:%S"),
                'MSISDN' : username,
                'Error_code': response.json()['header']['responseCode'],
                'Response'  : response.json(),
                'Reason'    : response.reason
                }
    else:
        response_json = {
                    'Timestamp' : datetime.now().strftime("%d-%m-%Y %H:%M:%S"),
                    'MSISDN' : username,
                    'Error_code': response.status_code,
                    'Response'  : response.reason
                }
    return response_json

def get_we_usage(username, password, isVerbose=True, logFile=log_file, isAlert=False, slackWebhook="", MBAlert=10, daysAlert=7):
    ## TE.EG URLs
    baseURL = "https://api-my.te.eg/api/"
    generateTokenAPI = "user/generatetoken?channelId=WEB_APP"
    loginAPI = "user/login?channelId=WEB_APP"
    usageAPI = "line/freeunitusage"

    # main header
    headers={'Content-Type': 'application/json'}
    response = handle_we_response("GET", baseURL+generateTokenAPI, headers, username)
    if response['Error_code'] == '0':
        headers['Jwt'] = response['Response']['body']['jwt']
        payload = {"header":{"msisdn": username,"numberServiceType":"FBB","locale":"en"},"body":{"password": password}}
        response = handle_we_response("POST", baseURL+loginAPI, headers, payload)
        if response['Error_code'] == "0":
            headers['Jwt'] = response['Response']['body']['jwt']
            response = handle_we_response("POST", baseURL+usageAPI, headers, payload, username)
            if response['Error_code'] == "0":
                remainingMB = response['Response']['body']['detailedLineUsageList'][0]['freeAmount']*1024
                totalMB = response['Response']['body']['detailedLineUsageList'][0]['initialTotalAmount']*1024
                endDate = response['Response']['body']['detailedLineUsageList'][0]['renewalDate']
                remainingDays = date(int(endDate.split('-')[0]), int(endDate.split('-')[1]), int(endDate.split('-')[2])) - date.today()
                response = {
                        'Timestamp' : datetime.now().strftime("%d-%m-%Y %H:%M:%S"),
                        'MSISDN' : username,
                        'Error_code': "0",
                        'Total MBs' : str(round(totalMB)),
                        'Remaining MBs' : str(round(remainingMB)) ,
                        'Remaining pct' : str(round((remainingMB*100)/totalMB))+"%",
                        'Remaining Days' : str(remainingDays.days)
                    }
    if isVerbose:            
        log_usage(logFile, str(response))
    if isAlert:
        send_alert_slack(slackWebhook, response, MBAlert, daysAlert)
    
    print(response)

alive = True
while alive:
    with open("config.yml", "r") as f:
        config = yaml.safe_load(f)
    if 'numbers.list' not in config:
        print("Missing numbers.list in config.yml!")
        alive = False
        break
    else:
        if 'logging.verbose' not in config:
            config['logging.verbose'] = True
        if 'logging.dest' not in config:
            config['logging.dest'] = ""
        if 'slack.alert' not in config:
            config['slack.alert'] = False
        if 'remaining.mb' not in config:
            config['remaining.mb'] = 10
        if 'remaining.days' not in config:
            config['remaining.days'] = 7
        if 'slack.alert' in config:
            if dict(config).get('slack.alert') == True and dict(config).get('slack.webhook') == None:
                print("Missing slack.webhook value!")
                alive = False
                break
            if dict(config).get('numbers.list') == None or len(config['numbers.list']) == 0:
                print("Missing numbers.list values!")
                alive = False
                break
            else:
                for number in range(len(config['numbers.list'])):
                    if config['numbers.list'][number][0] == "vodafone":
                        get_voda_usage(config['numbers.list'][number][1], 
                                    config['numbers.list'][number][2],
                                    config['logging.verbose'],
                                    config['logging.dest'],
                                    config['slack.alert'],
                                    config['slack.webhook'],
                                    config['remaining.mb'],
                                    config['remaining.days'])
                    elif config['numbers.list'][number][0] == "we":
                        get_we_usage(config['numbers.list'][number][1], 
                                    config['numbers.list'][number][2],
                                    config['logging.verbose'],
                                    config['logging.dest'],
                                    config['slack.alert'],
                                    config['slack.webhook'],
                                    config['remaining.mb'],
                                    config['remaining.days'])
                    else:
                        print("Company must be WE or Vodafone!")
                        alive = False
                        break
    time.sleep(3600)