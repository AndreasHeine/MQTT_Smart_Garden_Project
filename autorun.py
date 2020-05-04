'''
name: RPi_PLC
file: autorun.py
python: v2.7

author: andreas heine
date: 14.06.2018
version: v1.0 beta

@changelog:
@14.06.2018: v1.0 beta
@15.07.2018: v1.1 beta => general functions / spi interface for mcp3008
@22.07.2018: v1.2 beta => multithreading / shared_memory / user_log
@23.07.2018: v1.3 beta => conf / MQTT_SEND/RECV / MQTT buffer / exception start_new_thread failed
@30.07.2018: v1.4 beta => MQTT topic list / autorestart threads
'''

import thread #2.7: thread / 3.x: _thread
import time

conf={"MQTT_BROKER":"192.168.2.108", "MQTT_TOPICS":[]}
shared_memory={"thread1_run":False, "thread2_run":False, "thread3_run":False, "MQTT_SEND":[], "MQTT_RECV":[]}

conf["MQTT_TOPICS"]=["7CF0818"]

'''
#Sample for adding a message:
data={"topic":"", "message":""}
#Sample buffer:
"MQTT_SEND":[{"topic":"topic_a", "message":"1"},{"topic":"topic_b", "message":"100"},{"topic":"topic_c", "message":"15"}]
'''

########################################################################################################################
#thread 1: main
########################################################################################################################

def main_thread(conf):

    print("thread 1 started\n")

    '''
    main_thread:
    '''
    
    global shared_memory

    import time
    import datetime
    import RPi.GPIO as GPIO
    import Adafruit_GPIO.SPI as SPI
    import Adafruit_MCP3008

    #globals:
    GLOBVAR={} #global variables
    GLOBMSG={} #global messages
    GLOBIN={} #global input data
    GLOBOUT={} #global output data
    GLOBLOG={} #global log data
    GLOBTIMER={} #global timer data
    GLOBGPIO={} #global gpio data

    #init global variables:
    GLOBVAR["first_cycle"]=True
    GLOBVAR["stop"]=False
    GLOBVAR["cycletime"]=0.0 #[sec]
    GLOBVAR["cycletime_offset"]=0.2 #recommended values: 0.0s-1.5[sec]
    GLOBVAR["restarttime"]=5.0 #recommended values: 0.0-5.0[sec]
    GLOBVAR["auto_release"]=False
    GLOBVAR["diag"]=False
    GLOBVAR["rain"]=False
    GLOBVAR["light"]=False
    GLOBVAR["level"]=False
    GLOBVAR["wetness_1"]=False
    GLOBVAR["wetness_2"]=False
    GLOBVAR["wetness_3"]=False
    GLOBVAR["max_time"]=0
    GLOBVAR["switch_value"]=0
    GLOBVAR["start"]=False

    #init global messages:
    GLOBMSG["message"]=set() #init message as a set
    GLOBMSG["warning"]=set() #init warning as a set
    GLOBMSG["error"]=set() #init error as a set
    GLOBMSG["status"]="stop" #init status as a string "stop"
    GLOBMSG["logged"]=""

    #setup for the gpio's
    def user_gpio_setup(GLOBVAR, GLOBGPIO):

        '''
        user_gpio_setup:
        '''

        #gpio general setup:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

        #hc-sr04 (ultrsonicsensor):
        GLOBGPIO["trig"]=4
        GLOBGPIO["echo"]=18
        GPIO.setup(GLOBGPIO["trig"],GPIO.OUT)
        GPIO.output(GLOBGPIO["trig"], False) #init
        GPIO.setup(GLOBGPIO["echo"],GPIO.IN)

        #spi-Interface for mcp3008:
        SPI_PORT=0
        SPI_DEVICE=0
        GLOBGPIO["mcp3008_1"]=Adafruit_MCP3008.MCP3008(spi=SPI.SpiDev(SPI_PORT, SPI_DEVICE))

        #pump
        GLOBGPIO["pump_1"]=19
        GPIO.setup(GLOBGPIO["pump_1"], GPIO.OUT)
        GPIO.output(GLOBGPIO["pump_1"], False) #init
        
        '''
        user_gpio_setup end
        '''
        pass

    user_gpio_setup(GLOBVAR, GLOBGPIO) #setup for the gpio's

    #user program:
    def user_program(GLOBVAR, GLOBMSG, GLOBIN, GLOBOUT, GLOBTIMER, GLOBGPIO):
        
        '''
        user_program:
        '''

        global shared_memory

        #hc-sr04 (ultrasonicsensor):
        GPIO.output(GLOBGPIO["trig"], True)
        time.sleep(0.001)
        GPIO.output(GLOBGPIO["trig"], False)
        end=0
        start=0
        sig_time=0
        timeout=False
        timeout_time=time.time()
        while not GPIO.input(GLOBGPIO["echo"]):
            start=time.time()
            if (time.time()-timeout_time)>0.5:
                timeout=True
                break
        timeout_time=time.time()
        while GPIO.input(GLOBGPIO["echo"]):
            end=time.time()
            if (time.time()-timeout_time)>0.5:
                timeout=True
                break
        if not timeout:
            sig_time=end-start
            result=sig_time/0.000058 #distance in cm
            if result>0:
                GLOBIN["distance_1"]=result
            else:
                GLOBIN["distance_1"]=0
        else:
            #shared_memory["MQTT_SEND"].append("error/hc-sr04 timeout!")
            GLOBIN["distance_1"]=0
            pass
        
        #mcp3008 (8-channel-analog-digital-converter):
        values=[0]*8 #init list of 8 ints
        for i in range(8):
            values[i]=GLOBGPIO["mcp3008_1"].read_adc(i)  
        GLOBIN["mcp3008_1_ch1"]=values[0] #wetness-sensor 1
        GLOBIN["mcp3008_1_ch2"]=values[1] #wetness-sensor 2
        GLOBIN["mcp3008_1_ch3"]=values[2] #wetness-sensor 3
        GLOBIN["mcp3008_1_ch4"]=values[3] #rain-sensor
        GLOBIN["mcp3008_1_ch5"]=values[4] #brightness-sensor
        GLOBIN["mcp3008_1_ch6"]=values[5] #reserve
        GLOBIN["mcp3008_1_ch7"]=values[6] #reserve
        GLOBIN["mcp3008_1_ch8"]=values[7] #reserve

        #water-level (values in cm):
        if GLOBIN["distance_1"]>10:
            GLOBVAR["level"]=False
        else:
            GLOBVAR["level"]=True

        #light (0-1000):
        if GLOBIN["mcp3008_1_ch5"]>600:
            GLOBVAR["light"]=True
        elif GLOBIN["mcp3008_1_ch5"]<500:
            GLOBVAR["light"]=False

        #rain (0-1000):
        if GLOBIN["mcp3008_1_ch4"]<700:
            GLOBVAR["rain"]=True
        elif GLOBIN["mcp3008_1_ch4"]>850:
            GLOBVAR["rain"]=False

        #wetness-sensor 1 (0-1000):
        if GLOBIN["mcp3008_1_ch1"]>(GLOBVAR["switch_value"]+150):
            GLOBVAR["wetness_1"]=False
        elif GLOBIN["mcp3008_1_ch1"]<(GLOBVAR["switch_value"]-150):
            GLOBVAR["wetness_1"]=True
        '''
        #wetness-sensor 2 (0-1000):
        if GLOBIN["mcp3008_1_ch2"]>600:
            GLOBVAR["wetness_2"]=False
        elif GLOBIN["mcp3008_1_ch2"]<600:
            GLOBVAR["wetness_2"]=True
        
        #wetness-sensor 3 (0-1000):
        if GLOBIN["mcp3008_1_ch3"]>600:
            GLOBVAR["wetness_3"]=False
        elif GLOBIN["mcp3008_1_ch3"]<600:
            GLOBVAR["wetness_3"]=True
        '''

        #pump control:
        GLOBOUT["pump_1"]=not GLOBVAR["auto_release"] and GLOBVAR["start"]#GLOBVAR["level"] and not GLOBVAR["rain"] and not GLOBVAR["wetness_1"] and GLOBVAR["auto_release"] or not GLOBVAR["auto_release"] and GLOBVAR["start"] and GLOBVAR["level"]
        GPIO.output(GLOBGPIO["pump_1"], GLOBOUT["pump_1"])

        #diag:
        if GLOBVAR["diag"]:
            print("---")
            print("status: "+GLOBMSG["status"])
            print("inputs: "+repr(GLOBIN))
            print("outputs: "+repr(GLOBOUT))
            print("variablen: "+repr(GLOBVAR))                 
            print("message: "+str(GLOBMSG["message"]))
            print("warning: "+str(GLOBMSG["warning"]))
            print("error: "+str(GLOBMSG["error"]))
            print("MQTT_RECV: "+repr(shared_memory["MQTT_RECV"]))
            print("MQTT_SEND: "+repr(shared_memory["MQTT_SEND"]))

        if shared_memory["MQTT_RECV"]:
            for entry in shared_memory["MQTT_RECV"]:
                data=shared_memory["MQTT_RECV"][0].split("/")
                if data[0].decode("UTF-8")=="Betriebsart":
                    if data[1].decode("UTF-8")=="Auto":
                        GLOBVAR["auto_release"]=True
                        pass
                    elif data[1].decode("UTF-8")=="Hand":
                        GLOBVAR["auto_release"]=False
                        pass
                    shared_memory["MQTT_RECV"].pop(0)
                    pass
                elif data[0].decode("UTF-8")=="Zeit":
                    try:
                        GLOBVAR["max_time"]=int(data[1].decode("UTF-8"))
                    except:
                        pass
                    shared_memory["MQTT_RECV"].pop(0)
                    pass
                elif data[0].decode("UTF-8")=="Feuchte":
                    try:
                        GLOBVAR["switch_value"]=int(data[1].decode("UTF-8"))
                    except:
                        pass
                    shared_memory["MQTT_RECV"].pop(0)
                    pass
                elif data[0].decode("UTF-8")=="Hand":
                    if data[1].decode("UTF-8")=="Start":
                        GLOBVAR["start"]=True
                    elif data[1].decode("UTF-8")=="Stop":
                        GLOBVAR["start"]=False
                    shared_memory["MQTT_RECV"].pop(0)
                    pass
                else:
                    try:
                        shared_memory["MQTT_RECV"].pop(0)
                    except:
                        pass
                    
                '''
                data=shared_memory["MQTT_RECV"][0].split("/")
                if data[0]=="test":
                    GLOBVAR["test"]=int(data[1])
                    shared_memory["MQTT_RECV"].pop(0)
                elif data[0]=="auto_release":
                    if data[1]=="1":
                        GLOBVAR["auto_release"]=True
                    elif data[1]=="0":
                        GLOBVAR["auto_release"]=False
                    else:
                        pass
                    shared_memory["MQTT_RECV"].pop(0)
                else:
                    try:
                        shared_memory["MQTT_RECV"].pop(0)
                    except:
                        pass
                '''
                    
        '''
        user_program end
        '''
        pass

    def user_log(GLOBMSG):
        
        '''
        user_log:
        '''
        
        data=" m: "+str(GLOBMSG["message"])+" w: "+str(GLOBMSG["warning"])+" e: "+str(GLOBMSG["error"])
        if data!=GLOBMSG["logged"]:
            with open("log.txt", "a+") as file:
                GLOBMSG["logged"]=data
                file.write(str(datetime.datetime.now())+data+"\n")
                
        '''
        user_log end
        '''
        pass

    

    while True:
        while True:
            if GLOBVAR["stop"]:
                GLOBMSG["status"]="stop"
                GPIO.cleanup() #reset gpio setup
                if GLOBVAR["restarttime"]>0.0:
                    time.sleep(GLOBVAR["restarttime"])
                user_gpio_setup(GLOBVAR, GLOBGPIO) #setup for the gpio's
                user_log(GLOBMSG) #loging: message/warning/error
                GLOBMSG["message"]=set()
                GLOBMSG["warning"]=set()
                GLOBMSG["error"]=set()
                GLOBVAR["stop"]=False
                
            while not GLOBVAR["stop"]:
                time_value_1=time.time()
                user_program(GLOBVAR, GLOBMSG, GLOBIN, GLOBOUT, GLOBTIMER, GLOBGPIO) #user program
                GLOBVAR["first_cycle"]=False
                if GLOBMSG["error"]:
                    GLOBVAR["stop"]=True
                    GLOBVAR["auto_release"]=False
                if not GLOBVAR["stop"]:
                    GLOBMSG["status"]="run"
                if GLOBVAR["cycletime_offset"]>0.0:
                    time.sleep(GLOBVAR["cycletime_offset"])
                GLOBVAR["cycletime"]=time.time()-time_value_1
                if GLOBVAR["diag"]:
                    print("cycletime: "+str(GLOBVAR["cycletime"]))

    GPIO.cleanup()
    print("thread 1 exit\n")
    shared_memory["thread1_run"]=False
    thread.exit()
    '''
    main_thread end
    '''
    pass

########################################################################################################################
#thread 2: mqtt recv
########################################################################################################################

def mqtt_recv_thread(conf):

    print("thread 2 started\n")
    
    '''
    mqtt_recv_thread:
    '''
    
    global shared_memory
    
    import paho.mqtt.client as mqtt
     
    MQTT_BROKER=conf["MQTT_BROKER"]
    MQTT_TOPIC_LIST=conf["MQTT_TOPICS"]

    def on_connect(client, userdata, flags, rc):
        if rc==0:
            print("Connected to broker!\n")
            for each, entry in enumerate(MQTT_TOPIC_LIST):
                client.subscribe(MQTT_TOPIC_LIST[each])
                print("subscribed to: "+MQTT_TOPIC_LIST[each]+"\n")
        else:
            print("Connection failed!\n")
            pass

    def on_message(client, userdata, msg):
        shared_memory["MQTT_RECV"].append(str(msg.payload))
     
    client=mqtt.Client()
    client.on_connect=on_connect
    client.on_message=on_message
    client.connect(MQTT_BROKER, 1883, 60)
    client.loop_forever()

    print("thread 2 exit\n")
    shared_memory["thread2_run"]=False
    thread.exit()
    '''
    mqtt_recv_thread end
    '''
    pass

########################################################################################################################
#thread 3: mqtt send
########################################################################################################################

def mqtt_send_thread(conf):

    print("thread 3 started\n")
    
    '''
    mqtt_send_thread:
    '''
    
    global shared_memory
    
    import paho.mqtt.client as mqtt
    import time
     
    MQTT_BROKER=conf["MQTT_BROKER"]
    MQTT_TOPIC_LIST=conf["MQTT_TOPICS"]

    def on_connect(client, userdata, flags, rc):
        '''
        if rc==0:
            print("Connected to broker!\n")
            for each, entry in enumerate(MQTT_TOPIC_LIST):
                client.subscribe(MQTT_TOPIC_LIST[each])
                print("subscribed to: "+MQTT_TOPIC_LIST[each]+"\n")
        else:
            print("Connection failed!\n")
            pass
        '''
        pass

    def on_publish(client, userdata, mid):
        pass
     
    client=mqtt.Client()
    client.on_connect=on_connect
    client.on_publish=on_publish
    client.connect(MQTT_BROKER, 1883, 60)

    try:
        while True:
            client.loop_start()
            while True:
                time.sleep(0.5)
                for each, entry in enumerate(shared_memory["MQTT_SEND"]):
                    MQTT_PATH=shared_memory["MQTT_SEND"][each]["topic"]
                    MQTT_MSG=shared_memory["MQTT_SEND"][each]["message"]
                    (rc, mid)=client.publish(MQTT_PATH, MQTT_MSG, qos=1)
                    shared_memory["MQTT_SEND"].pop(0)
            client.loop_stop()
    except:
        client.disconnect()

    print("thread 3 exit\n")
    shared_memory["thread3_run"]=False
    thread.exit()    
    '''
    mqtt_send_thread end
    '''
    pass

########################################################################################################################
#start all threads:
########################################################################################################################

if __name__=='__main__':
    while True:
        if not shared_memory["thread1_run"]:
            shared_memory["thread1_run"]=True
            try:
                thread.start_new_thread(main_thread, (conf, ))
            except:
                shared_memory["thread1"]=False
                print ("Error: unable to start all thread 1\n")
        if not shared_memory["thread2_run"]:
            shared_memory["thread2_run"]=True
            try:
                thread.start_new_thread(mqtt_recv_thread, (conf, ))
            except:
                shared_memory["thread2_run"]=False
                print ("Error: unable to start all thread 2\n")
        if not shared_memory["thread3_run"]:
            shared_memory["thread3_run"]=True
            try:
                thread.start_new_thread(mqtt_send_thread, (conf, ))
            except:
                shared_memory["thread3_run"]=False
                print ("Error: unable to start all thread 3\n")
        while True:
            if not shared_memory["thread1_run"] or not shared_memory["thread2_run"] or not shared_memory["thread3_run"]:
                break

    print("main thread end\n")

while True:
    time.sleep(1)
    pass
