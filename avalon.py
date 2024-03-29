from collections import UserList
from curses.ascii import US
import time
import serial
import smbus
from digi.xbee.devices import XBeeDevice
from digi.xbee.devices import RemoteXBeeDevice
from digi.xbee.models.address import XBee64BitAddress, XBee16BitAddress, XBeeIMEIAddress
import enum
import os
import digi.xbee.exception
from digi.xbee.comm_interface import XBeeCommunicationInterface
from digi.xbee.models.atcomm import SpecialByte
from digi.xbee.models.mode import OperatingMode
from digi.xbee.packets.base import XBeeAPIPacket, XBeePacket
from digi.xbee.util import utils
import json
import threading
import pymodbus
import serial
import time
from pymodbus.pdu import ModbusRequest
from pymodbus.client import ModbusSerialClient as ModbusClient 
#from pymodbus.client.sync import ModbusSerialClient as ModbusClient
import gpiod


# Initiate all the common parameters here/ setting here
bus = smbus.SMBus(3)               # Zeta 3.0 uses I2c bus no 3 to communicate with Battery charger and Temperature sensor
#gps = serial.Serial()
#gps.port = "/dev/ttyUSB4"          #If connected to USB_U refer schematic
#gps.baudrate = 9600                # GPS (Inverteck systems Baud rate 9600 if TFRobot 115200)
mcu = serial.Serial()
mcu.port = "/dev/ttyUSB2"          #MCU connected to USB2
mcu.baudrate = 115200              #For MCU
mcu.open()
gps = serial.Serial()
gps.port = "/dev/ttyACM0"          #If connected to USB_U refer schematic
gps.baudrate = 9600                # GPS (Inverteck systems Baud rate 9600 if TFRobot 115200)
# Wind Sensor Modbus RTU interface
client= ModbusClient(method = "rtu", port="/dev/verdin-uart1",stopbits = 1, bytesize = 8, parity = 'N', baudrate= 9600)
# For Battery Charger
LTC4015 = 0x68          # LTC4015 connected to i2c bus no 3. And address is on hardware refer schematics 
# GPIO Configuration
chip = gpiod.chip(0)
xbee1 = chip.get_line(11)
config = gpiod.line_request()
config.request_type = gpiod.line_request.DIRECTION_OUTPUT
xbee1.request(config)
#xbee1.set_value(1)
xbee2 = chip.get_line(8)
config = gpiod.line_request()
config.request_type = gpiod.line_request.DIRECTION_OUTPUT
xbee2.request(config)
#xbee2.set_value(1)      
# For below Adress refer data sheet 
VBAT = 0x3A
IBAT = 0x3D
VIN  = 0x3B
IIN  = 0x3E
VSYS = 0x3C
DIE_TEMP = 0x3F
STATUS = 0x39
CON_BIT = 0x14 
QCOUNT = 0x13
QCOUNT_PRE_FACTOR = 0x12
CHARGER_STATE = 0x34
# Global Decleartions 
RSNSA = 4     # 4 miliohm 
RSNSB = 10    # 10 miliohm
# Calculated values 
QCount_Prescalr = 27.47 # refer the calculation sheet
#Wireless Communication
PORT = "/dev/verdin-uart2"                         # Board to PC Communication Xbee with F2A Pan ID
BAUD_RATE = 115200                                   # Both xbee configured with 9600 Baud trate & Coordinator 
device1 = XBeeDevice(PORT, BAUD_RATE)               # PC to Board communication (PC has a Router configuration)
PORT1 = "/dev/ttyUSB3"
device2 = XBeeDevice(PORT1, BAUD_RATE)             # Board to Rover 1.0 communication

def Batt_Charger_Operation_Status():
    Con_data = bus.read_i2c_block_data(LTC4015, CON_BIT,2)
    Con_data = Con_data[1]  << 8 | Con_data[0]
    if (Con_data & 1 << 8):
        print("Battery Charger operation suspended")
        result = 0
    else:
        result = 1
        print("Battery charger in operation ")
    return result

def Batt_Charger_Operation_Enable():
    Con_data = bus.read_i2c_block_data(LTC4015, CON_BIT,2)
    Con_data = Con_data[1]  << 8 | Con_data[0]              # merge 2 8 bit data to 16bit data 
    if (Con_data & 1 << 8):
        Con_data  = Con_data & 0 << 8                       # Set the 8th bit to 0 to enable battery charging 
        data1 =  (Con_data >> 8) & 0xFF                     # Split 16bit data to 2 8bit data data1 is MSB, data0 is LSB
        data0 =  Con_data & 0xFF
        data = [data0, data1]
        bus.write_i2c_block_data(LTC4015, CON_BIT, data )
        Con_data = bus.read_i2c_block_data(LTC4015, CON_BIT,2)
        Con_data = Con_data[1]  << 8 | Con_data[0]
        if (Con_data & 1 << 8):
            print("Battery charger set to charge")
            result = 1
        else :
            print("Failed to Enable the battery charger ")
            print("After fail of bit 8 Configuration bits in Hex :", hex(Con_data))
            result = 2                                     # if failed on Enable
    else:
        print("Battery charger in operation ")
        result = 3                                           # if alreadu in operation 
    return result

def Mesurement_System_Status():
    Con_data = bus.read_i2c_block_data(LTC4015, CON_BIT,2)
    Con_data = Con_data[1]  << 8 | Con_data[0]
    if (Con_data & 1 << 4):
        print("Measurement System ON")
        result = 1
    else:
        print("Measurement System OFF ")
        result =0
    return result

def Mesurement_System_Enable():
    Con_data = bus.read_i2c_block_data(LTC4015, CON_BIT,2)
    Con_data = Con_data[1]  << 8 | Con_data[0]  
    if (Con_data & 1 << 4):
        print("Measurement System ON")
        result = 3
    else:
        print("Measurement System OFF  so ON now ")
        Con_data |=  1 << 4 
        data1 =  (Con_data >> 8) & 0xFF
        data0 =  Con_data & 0xFF
        data = [data0, data1]
        bus.write_i2c_block_data(LTC4015, CON_BIT, data )
        Con_data = bus.read_i2c_block_data(LTC4015, CON_BIT,2)
        Con_data = Con_data[1]  << 8 | Con_data[0]          # merge 2 8 bit data to 16bit data 
        if (Con_data & 1 << 4):
            print("Measurement System ON")
            result = 1
        else:
            print("Failed to ON the measurementsystem")
            print("After fail of bit 4 Configuration bits in Hex :", hex(Con_data))
            result = 2
    return result

def Columb_Counter_Status():
    Con_data = bus.read_i2c_block_data(LTC4015, CON_BIT,2)
    Con_data = Con_data[1]  << 8 | Con_data[0]
    if (Con_data & 1 << 2):
        print("Colum Counter ON")
        result = 1
    else:
        print("Colum Counter OFF")
        result = 0
    return result

def Columb_Counter_Enable():
    Con_data = bus.read_i2c_block_data(LTC4015, CON_BIT,2)
    Con_data = Con_data[1]  << 8 | Con_data[0]
    if (Con_data & 1 << 2):
        print("Colum Counter ON")
        result = 3
    else:
        print("Colum Counter OFF So ON Now")
        Con_data |=  1 << 2
        data1 =  (Con_data >> 8) & 0xFF
        data0 =  Con_data & 0xFF
        data = [data0, data1]
        bus.write_i2c_block_data(LTC4015, CON_BIT, data )
        Con_data = bus.read_i2c_block_data(LTC4015, CON_BIT,2)
        Con_data = Con_data[1]  << 8 | Con_data[0]                                   # merge 2 8 bit data to 16bit data 
        if (Con_data & 1 << 2):
            print("Colum Counter ON")
            result = 1
        else:
            print("Failed to ON the Colum counter")
            print("After fail of bit 2 Configuration bits in Hex :", hex(Con_data))
            result = 2
    return result

def Read_SOC_Configuration():
    Qcount_Prescalor_factor = bus.read_i2c_block_data(LTC4015, QCOUNT_PRE_FACTOR, 2)
    Qcount_Prescalor_factor = Qcount_Prescalor_factor[1]  << 8 | Qcount_Prescalor_factor[0]
    print("Qcount_Prescalor_factor :",Qcount_Prescalor_factor)
    Qcount = bus.read_i2c_block_data(LTC4015, QCOUNT, 2)
    Qcount = Qcount[1]  << 8 | Qcount[0]
    print("Qcount :",Qcount)

def SOC_Configuration():
    status = Columb_Counter_Status()
    if status == 1:
        data = 512
        data1 =  (data >> 8) & 0xFF
        data0 =  data & 0xFF
        data = [data0, data1]
        bus.write_i2c_block_data(LTC4015, QCOUNT_PRE_FACTOR, data )
        Qcount_Prescalor_factor = bus.read_i2c_block_data(LTC4015, QCOUNT_PRE_FACTOR, 2)
        Qcount_Prescalor_factor = Qcount_Prescalor_factor[1]  << 8 | Qcount_Prescalor_factor[0]
        if Qcount_Prescalor_factor == 27:
            #print("Qcount_Prescalor_Factor write success")
            result =1
        else:
            #print("Qcount_Prescalor_Factor write Fail")
            result =0
    else:
        result = status
    return result

def SOC_Calculate():
    Qcount = bus.read_i2c_block_data(LTC4015, QCOUNT, 2)
    Qcount = Qcount[1]  << 8 | Qcount[0]
    value = int(Qcount)
    SOC = ((value - 32768) / 3459) * 100
    return  round(SOC,2)
    
def Batt_Connection_Status():
    State = bus.read_i2c_block_data(LTC4015,CHARGER_STATE, 2)
    State =State[1]  << 8 | State[0]
    if (State & 1 << 1):
        print("Battery Not Connected")
        status = 0
    else:
        status = 1
    return status

def twos_comp(val, bit):
    if val >= 2**bit:
        print("Data out of range")
    else:
        return val - int((val << 1) & 2**bit)

def Gps_Read():
    try:
        gps.open()
        print("GPS Port opened ")
        response = ""                                     # Used to hold data coming over UART
        time.sleep(2)
        response = gps.readline(gps.in_waiting)
        print("read data: ",response,"\n")
        file = open('log.txt','a')
        file.write('\n')
        file.write(str(int(time.time())))
        file.write('\t')
        file.write(str(response))
        file.flush
        file.close
        response = "File saved"
        gps.close()
        print("GPS port closed after reading data")
        return response
    except:
        print("GPS port open attempt failed!")
        response = "GPS port open attempt failed! & port closed"
        gps.close()
        return response

def Sensor_read():
    try:
        response = ""
        time.sleep(1)
        response = mcu.readline(mcu.in_waiting)
        print("read data: ",response)
        file = open('log.txt','a')
        file.write('\n')
        file.write(str(int(time.time())))
        file.write('\t')
        file.write(str(response))
        file.flush
        file.close
    except:
        mcu.close()
        time.sleep(3)
        mcu.open()

def Board_Power():
    System = Mesurement_System_Status()
    if System == 1:
        Input_Voltage = bus.read_i2c_block_data(LTC4015, VIN ,2)
        Input_Voltage= Input_Voltage[1]  << 8 | Input_Voltage[0] 
        Input_Voltage = Input_Voltage * 0.001648 
        print("Measured Input Voltage is :",Input_Voltage )
        Input_Current= bus.read_i2c_block_data(LTC4015, IIN,2)
        Input_Current= Input_Current[1]  << 8 | Input_Current[0] 
        Input_Current =((Input_Current*1.46487)/4)/1000
        print("Measured Input Current is :",Input_Current,"A")
        VSYS_Voltage = bus.read_i2c_block_data(LTC4015, VSYS ,2)
        VSYS_Voltage= VSYS_Voltage[1]  << 8 | VSYS_Voltage[0] 
        VSYS_Voltage = VSYS_Voltage * 0.001648 
        print("Measured System Voltage is :",VSYS_Voltage )
        Die_Temp = bus.read_i2c_block_data(LTC4015, DIE_TEMP ,2)
        Die_Temp= Die_Temp[1]  << 8 | Die_Temp[0] 
        Die_Temp = (Die_Temp - 12010)/45.6 
        print("Measured Die Temperature is :",Die_Temp,"degC")
    else:
        Mesurement_System_Enable()
        Input_Voltage ="-NA-"
        Input_Current ="-NA-"
        VSYS_Voltage ="-NA-"
        Die_Temp ="-NA-"
    System = Batt_Connection_Status()
    if System == 1:
        Batter_Voltage = bus.read_i2c_block_data(LTC4015, VBAT,2)
        Batter_Voltage= Batter_Voltage[1]  << 8 | Batter_Voltage[0] 
        Batter_Voltage = Batter_Voltage * 0.000192264 * 7
        print("Measured Battery voltage is :",Batter_Voltage )
        Batt_Current= bus.read_i2c_block_data(LTC4015, IBAT ,2)
        Batt_Current= Batt_Current[1]  << 8 | Batt_Current[0] 
        if (Batt_Current & 1<<15):
            Batt_Current = twos_comp(Batt_Current, 16)              # 16 -> represent 16 bit value 
        Batt_Current =((Batt_Current*1.46487)/10)/1000
        print("Measured BatteryCurrent is :",Batt_Current,"A")
    else:
        Batter_Voltage = "-NA-"
        print("Measured Battery voltage is :",Batter_Voltage )
        Batt_Current = "-NA-"
        print("Measured BatteryCurrent is :",Batt_Current,"A")
    Battery_Charge = SOC_Calculate()
    print("Calculated Battery Charge  is: ",Battery_Charge,"%")
    file = open('log.txt','a')
    file.write('\n')
    file.write(str(int(time.time())))
    file.write('\t')
    file.write(str(Input_Voltage))
    file.write('\t')
    file.write(str(Input_Current))
    file.write('\t')
    file.write(str(Batter_Voltage))
    file.write('\t')
    file.write(str(Batt_Current))
    file.write('\t')
    file.write(str(VSYS_Voltage))
    file.write('\t')
    file.write(str(Die_Temp))
    file.write('\t')
    file.write(str(Battery_Charge))
    file.flush
    file.close
    
def System_Status():
    TS = str(int(time.time()))
    CMD = "SSTAT"
    try:
        CPU_Temp = open("/sys/devices/virtual/thermal/thermal_zone0/temp","r")
        CPU_Temp = int(CPU_Temp.read())/1000
    except:
        CPU_Temp = "-NA-"
    B_Temp = open("/sys/class/hwmon/hwmon0/temp1_input","r")
    B_Temp = int(B_Temp.read())/1000
    file = open('log.txt','a')
    file.write('\n')
    file.write(str(int(time.time())))
    file.write('\t')
    file.write("System")
    file.write('\t')
    file.write(str(CPU_Temp))
    file.write('\t')
    file.write(str(B_Temp))
    print("Time Stamp:",TS,"CPU Temp:",CPU_Temp,"Board Temp:",B_Temp)

def recieve_xbee1():
    xbee_message = device1.read_data()
    if xbee_message:
        data = xbee_message.data.decode("utf8")
        print("xbee1 RX:",data)
        file = open('xbee1.txt','a')
        file.write('\n')
        file.write(str(int(time.time())))
        file.write('\t')
        file.write(str(data))
        file.flush
        file.close

def rec_Msg1():
    print("Xbee1 rx thread started")
    while True:
        recieve_xbee1()

def recieve_xbee2():
    xbee_message = device2.read_data()
    if xbee_message:
        data = xbee_message.data.decode("utf8")
        print("xbee2 RX:",data)
        file = open('log.txt','a')
        file.write('\n')
        file.write(str(int(time.time())))
        file.write('\t')
        file.write(str(data))
        file.flush
        file.close

def rec_Msg2():
    print("Xbee2 rx thread started")
    while True:
        recieve_xbee2()
    
def Wind():
    connection = client.connect()
    print("Wind Sensor Port opent status:",connection)
    try:
        result= client.read_holding_registers(0x00,2,unit= 0x01)# starting address, no of registers, device ID(sensor address)
        b=result.registers[0]
        c=(b/100)
        print("Wind Speed :",c,"m/s")
        d=result.registers[1]
        print("Wind direction",d,"deg")
        file = open('log.txt','a')
        file.write('\n')
        file.write(str(int(time.time())))
        file.write('\t')
        file.write(str(c))
        file.write('\t')
        file.write(str(d))
        file.flush
        file.close
        client.close()
    except:
        print("Error in reading wind data")
        client.close()

def xbee1_Status():
    DATA = '{"TS":"1544163610","DID":"00000","CMD":"HST2","CID":12345}'
    #DATA = '{"TS":"1544163610","DID":"00000","CMD":"HINF"}'
    device1.send_data_broadcast(DATA)
    print("TX Xbee_01:",DATA)

def xbee2_Status():
    HST3 = {"TS":"1544163610","DID":"00000","CMD":"HST3","CID":12345}
    #DATA = '{"TS":"1544163610","DID":"00000","CMD":"HINF"}'
    device2.send_data_broadcast(json.dumps(HST3))
    print("TX Xbee_02:",HST3)

def Read_Xbee_Config():
    print("-----------------------------------------------")
    pan_id_dev2 = device2.get_pan_id()
    pan_id_dev1 = device1.get_pan_id()
    print("PAN_ID of Xbee1 :",pan_id_dev1.hex())
    print("PAN_ID of Xbee2 :",pan_id_dev2.hex())
    print("-----------------------------------------------")
    Stack_dev2 = device2.get_parameter("ZS")
    Stack_dev1 = device1.get_parameter("ZS")
    print("Stack Profile of Xbee1 :",Stack_dev1.hex())
    print("Stack Profile of Xbee2 :",Stack_dev2.hex())
    print("-----------------------------------------------")
    Op_pan_id_dev2 = device2.get_parameter("OI")
    Op_pan_id_dev1 = device1.get_parameter("OI")
    print("16_bit_OP_PAN_ID of Xbee1 :",Op_pan_id_dev1.hex())
    print("16_bit_OP_PAN_ID of Xbee2 :",Op_pan_id_dev2.hex())
    print("-----------------------------------------------")

def Write_PANID():
    print("1: Xbee1 PANID Change")
    print("2: Xbee2 PANID Change")
    User_Input = input("Enter your choice from 1 or 2:")
    if User_Input == "1":
        try:
            User_Input = input("Enter PANID for Xbee 1 :")
            print("User PANID Input is :",User_Input)
            apply_changes_enabled = device1.is_apply_changes_enabled()
            if apply_changes_enabled:
                device1.enable_apply_changes(False)
            try:
                device1.set_pan_id(utils.hex_string_to_bytes(User_Input))
            except Exception as e:
                print(e.__class__)
            try:
                device1.apply_changes()
            except Exception as e:
                print(e.__class__)
            try:
                device1.write_changes()
            except Exception as e:
                print(e.__class__)
            print("Apply Changes - - -")
            time.sleep(3)
            #pan_id_dev1 = device1.get_pan_id()
            print("PAN_ID of Xbee1 Changed")
        except:
            print("error writing PANID for xbee 1")
    if User_Input == "2":
        try:
            User_Input = input("Enter PANID for Xbee 2 :")
            print("User PANID Input is :",User_Input)
            apply_changes_enabled = device2.is_apply_changes_enabled()
            if apply_changes_enabled:
                device2.enable_apply_changes(False)
            try:
                device2.set_pan_id(utils.hex_string_to_bytes(User_Input))
            except Exception as e:
                print(e.__class__)
            try:
                device2.apply_changes()
            except Exception as e:
                print(e.__class__)
            try:
                device2.write_changes()
            except Exception as e:
                print(e.__class__)
            print("Apply Changes - - -")
            time.sleep(3)
            pan_id_dev2 = device2.get_pan_id()
            print("PAN_ID of Xbee2 Changed")
        except:
            print("error writing PANID for xbee 2")

def Write_Stack():
    print("1: Xbee1 Stack Profile Change")
    print("2: Xbee2 Stack Profile Change")
    User_Input = input("Enter your choice from 1 or 2:")
    if User_Input == "1":
        try:
            print("To Communicate with Rover 1.0 use Stack profile 0 ")
            print("To Communicate with Rover 3.0 use Stack profile 2 ")
            User_Input = input("User Input:")
            device1.set_parameter("ZS", utils.hex_string_to_bytes(User_Input))
            device1.execute_command("AC")
            print("Apply Changes ----")
            time.sleep(3)
            Stack_dev1 = device1.get_parameter("ZS")
            print("Stack Profile of Xbee1 :",Stack_dev1.hex())
        except Exception as e:
            print(e.__class__)
    if User_Input == "2":
        try:
            print("To Communicate with Rover 1.0 use Stack profile 0 ")
            print("To Communicate with Rover 3.0 use Stack profile 2 ")
            User_Input = input("User Input:")
            device2.set_parameter("ZS",utils.hex_string_to_bytes(User_Input))
            device2.execute_command("AC")
            print("Apply Changes ----")
            time.sleep(3)
            Stack_dev2 = device2.get_parameter("ZS")
            print("Stack Profile of Xbee2 :",Stack_dev2.hex())
        except Exception as e:
            print(e.__class__)
            
def Change_Stack_Remote_Dev():
    print("Rover1 Paired with Zeta Xbee 1 or 2, 1 for Xbee1, 2 for Xbee 2")
    User_Input = input("Enter your choice from 1 or 2:")
    if User_Input == "1":
        print("Communication to a specific Rover or to a Group")
        print("For Speific Rover select 1 for Multiple Rover select 2")
        User_Input2 = input("Enter your choice from 1 or 2:")
        if User_Input2 == "1":
            User_Input2 = input("Enter Device ID:")
            User_Input3 = input("Enter The stack Profile number 0 or 2")
            if User_Input3 == "0":
                Data = {"TS":str(int(time.time())),"DID":User_Input2,"CMD":"HZSP","VALUES":"0"}
                print ("Command to send :",Data)
                device1.send_data_broadcast(json.dumps(Data))
            if User_Input3 == "2":
                Data = {"TS":str(int(time.time())),"DID":User_Input2,"CMD":"HZSP","VALUES":"2"}
                print ("Command to send :",Data)
                device1.send_data_broadcast(json.dumps(Data))
        if User_Input2 == "2":
            User_Input = input("Enter The stack Profile number 0 or 2")
            if User_Input2 == "0":
                Data = {"TS":str(int(time.time())),"DID":"00000","CMD":"HZSP","VALUES":"0"}
                print ("Command to send :",Data)
                device1.send_data_broadcast(json.dumps(Data))
            if User_Input2 == "2":
                Data = {"TS":str(int(time.time())),"DID":"00000","CMD":"HZSP","VALUES":"2"}
                print ("Command to send :",Data)
                device1.send_data_broadcast(json.dumps(Data))
    if User_Input == "2":
        print("Communication to a specific Rover or to a Group")
        print("For Speific Rover select 1 for Multiple Rover select 2")
        User_Input = input("Enter your choice from 1 or 2:")
        if User_Input == "1":
            User_Input = input("Enter Device ID:")
            print("User Device ID:",User_Input)
            User_Input = input("Enter The stack Profile number 0 or 2")
            if User_Input == "0":
                Data = {"TS":str(int(time.time())),"DID":User_Input,"CMD":"HZSP","VALUES":"0"}
                print ("Command to send :",Data)
                device2.send_data_broadcast(json.dumps(Data))
            if User_Input == "2":
                Data = {"TS":str(int(time.time())),"DID":User_Input,"CMD":"HZSP","VALUES":"2"}
                print ("Command to send :",Data)
                device2.send_data_broadcast(json.dumps(Data))
        if User_Input == "2":
            User_Input = input("Enter The stack Profile number 0 or 2")
            if User_Input == "0":
                Data = {"TS":str(int(time.time())),"DID":"00000","CMD":"HZSP","VALUES":"0"}
                print ("Command to send :",Data)
                device2.send_data_broadcast(json.dumps(Data))
            if User_Input == "2":
                Data = {"TS":str(int(time.time())),"DID":"00000","CMD":"HZSP","VALUES":"2"}
                print ("Command to send :",Data)
                device2.send_data_broadcast(json.dumps(Data))

def xbee_reset():
    xbee1.set_value(0)   # Set value 0 Reset the xbee continiously 
    xbee2.set_value(0)
    print("GPIO Reset for 15 seconds")
    time.sleep(15)
    xbee1.set_value(1)   # Set value 0 Reset the xbee continiously 
    xbee2.set_value(1)
    print("GPIO Normal")
            
            
    

if __name__ == "__main__":
    print("Voyager Zone Controller Started")
    print("Initialising all parameters.....")
    time.sleep(3)
    # Initialising Xbee Comms
    xbee1.set_value(1)   # Set value 0 Reset the xbee continiously 
    xbee2.set_value(1)   # Set value 0 Reset the xbee continiously
    try:
        device1.open()
        print("Communication Established with xbee1 device")
    except:
        print("Couldn't initiate communication with xbee1")
    try:
        device2.open()
        print("communication Established with xbee2 device")
    except:
        print("Couldn't initiate communication with xbee2")
    # Check all power parameters
    Columb_Counter_Status()
    Columb_Counter_Enable()
    SOC_Configuration()
    Batt_Charger_Operation_Enable()
    # initiate threads
    rec_Msg1_thread=threading.Thread(target=rec_Msg1)
    rec_Msg1_thread.start()
    rec_Msg2_thread=threading.Thread(target=rec_Msg2)
    rec_Msg2_thread.start()
    while True:
        print("1: Xbee1 Transmit Data")
        print("2: Xbee2 Transmit Data")
        print("3: Battery Charger & Battery")
        print("4: Read GPS")
        print("5: Read CPU & Board Temperature")
        print("6: Read Sensor port")
        print("7: Read Wind Sensor")
        print("8: Read Xbee Configuration")
        print("9: Change Xbee PANID")
        print("10: Change Xbee Stack Profile") 
        print("11: Change Rover 1 Stack Profile over zigbee")
        print("12: Xbee Hard Reset(Both Xbee)")
        User_Input = input("Enter your choice from 1 to 12:")
        if User_Input == "1":
            try:
                xbee1_Status()
            except:
                print("error sending data for xbee 1")
        if User_Input == "2":
            try:
                xbee2_Status()
            except:
                print("error sending data for xbee 2")
        if User_Input == "3":
            try:
                Batt_Charger_Operation_Enable()
                Board_Power()
            except:
                print("error reading")
        if User_Input == "4":
            try:
                Gps_Read()
            except:
                print("error reading")
        if User_Input == "5":
            try:
                System_Status()
            except:
                print("error reading")
        if User_Input == "6":
            try:
                Sensor_read()
            except:
                print("error reading")
        if User_Input == "7":
            try:
                Wind()
            except:
                print("error reading")
        if User_Input == "8":
            try:
                Read_Xbee_Config()
            except:
                print("error reading xbee configuration")
        if User_Input == "9":
            try:
                Write_PANID()
            except:
                print("error writing PANID")
        if User_Input == "10":
            try:
                Write_Stack()
            except:
                print("error writing stack profile")
        if User_Input == "11":
           try:
               Change_Stack_Remote_Dev()
           except:
               print("error changing Remote Rover stack profile") 
        if User_Input == "12":
            try:
                xbee_reset()
            except:
                print("error reset xbee") 
