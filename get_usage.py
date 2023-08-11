import requests
import json
import time
from threading import Thread
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from datetime import datetime, date

webhook = ""
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
def get_voda_usage(username, password):
    try:
        options = Options()
        options.add_argument('--headless=new')
        options.add_experimental_option('excludeSwitches', ['enable-logging'])


        driver = webdriver.Chrome(options=options)
        driver.get('https://web.vodafone.com.eg/spa/redHome')
        driver.get(driver.current_url)
        time.sleep(1)
        usernameElement = driver.find_element(By.ID, 'username')
        usernameElement.send_keys(username)
        passwordElement = driver.find_element(By.ID, 'password')
        passwordElement.send_keys(password)
        time.sleep(1)
        btnElement = driver.find_element(By.ID, 'submitBtn')
        btnElement.click()
        time.sleep(2)
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
    except:
        response = {
                    'Timestamp' : datetime.now().strftime("%d-%m-%Y %H:%M:%S"),
                    'MSISDN' : username,
                    'Error_code': "500",
                    'Response'  : "Something went wrong!"
                }
    send_alert_slack(webhook, response)
    log_usage(log_file, str(response))
    #return response



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

def get_we_usage(username, password):
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
                
    send_alert_slack(webhook, response)
    log_usage(log_file, str(response))
    #return response


while True:
    t1 = Thread(target=get_voda_usage("", ""))
    t1.start()
    t2 = Thread(target=get_voda_usage("", ""))
    t2.start()
    t3 = Thread(target=get_voda_usage("", ""))
    t3.start()
    t4 = Thread(target=get_we_usage("" ,""))
    t4.start()
    time.sleep(3600)
