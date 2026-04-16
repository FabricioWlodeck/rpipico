import time
import network
import ubinascii
from mqtt_as import MQTTClient
from mqtt_local import config
import uasyncio as asyncio
import dht, machine
import json

# las pruebas reales fueron realizadas con un sensor DHT11
sensor = dht.DHT11(machine.Pin(15)) 
ID_DISPOSITIVO = ""
led_pico = machine.Pin("LED", machine.Pin.OUT)
pin_rele = machine.Pin(14, machine.Pin.OUT)


#---------- Obtengo la Mac la cual uso como ID ----------
async def obtener_id_mac():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True) # Es necesario activar la interfaz para leer la config
    # Obtenemos la MAC y la convertimos a string
    while not wlan.active(): pass
    mac_raw = wlan.config('mac')
    mac = ubinascii.hexlify(mac_raw, ':').decode()
    return mac

#---------- Funciones ----------
def cargar_datos():
    global parametros
    try:
        with open("parametros.json", "r") as f:
            parametros = json.load(f)
        print("Configuración cargada desde el archivo.")
    except (OSError, ValueError):
        print("Sin datos guardados. Usando valores por defecto.")
        parametros = {
            "setpoint": 26.0,
            "periodo": 10,
            "modo": "auto",
            "rele": 0
        }

# EJECUTAMOS LA CARGA (Sin await, porque es una función normal)
cargar_datos()

async def up(client, evento_suscrito):  # Respond to connectivity being (re)established
    global ID_DISPOSITIVO
    while True:
        await client.up.wait()  # Wait on an Event
        client.up.clear()
        await client.subscribe(f"{ID_DISPOSITIVO}/setpoint", 1)
        await client.subscribe(f"{ID_DISPOSITIVO}/periodo", 1)
        await client.subscribe(f"{ID_DISPOSITIVO}/modo", 1)
        await client.subscribe(f"{ID_DISPOSITIVO}/rele", 1)
        await client.subscribe(f"{ID_DISPOSITIVO}/destello", 1)
        print(f"Suscripto a los 5 topicos")
        evento_suscrito.set()

async def destello():
    for _ in range(10):
        led_pico.toggle()
        await asyncio.sleep_ms(200)
    led_pico.off()


async def guardar_parametros(config):
    try:
        with open("parametros.json", "w") as f:
            json.dump(config, f)
    except OSError:
        print("Error guardando en flash")

async def messages(client):  # Respond to incoming messages
    # global setpoint, periodo, modo, rele
    async for topic, msg, retained in client.queue:
        topico = topic.decode()
        mensaje = msg.decode()

        print(f"comando recibido: {topico} -> {mensaje}")
        
        cambios = False # con esta bandera se cuando hay cambios para actulizar

        if topico.endswith("/setpoint"):
            #setpoint = float(mensaje)
            parametros["setpoint"] = float(mensaje)
            cambios=True
            print(f"\n   Cambio de setpoint a: {parametros["setpoint"]}\n")


        if topico.endswith("/periodo"):
            #periodo = int(mensaje)
            parametros["periodo"] = int(mensaje)
            cambios=True

        if topico.endswith("/modo"):
            #modo = str(mensaje)
            parametros["modo"] = str(mensaje)
            cambios=True
            print(f"\n   Cambio de modo a: {parametros["modo"]}\n")


        if topico.endswith("/rele"):
            rele = mensaje
            if rele == "1":
                parametros["rele"] = True
            else:
                parametros["rele"] = False
            print(f"\n   Cambio de luz del rele a: {parametros["rele"]}\n")

            cambios=True
            print(f"\n   [ ¡¡¡¡¡ RELEE !!!!! ]\n")

        if topico.endswith("/destello"):
            asyncio.create_task(destello())
            print(f"\n[ ¡¡¡¡¡ DESTELLOOOO !!!!! ]\n")

        if cambios == True:
           await guardar_parametros(parametros)
           print("Archivo parametros.json actualizado con éxito.")

async def rele_modo(parametros): 
    while True:
        modo = parametros.get("modo", "auto")
        temp = parametros.get("temperatura", 0)
        sp = parametros.get("setpoint", 26.0)
        rele = parametros.get("rele", False)

        if modo == "auto":
            if temp > sp:
                pin_rele.value(1)
            else:
                pin_rele.value(0)
 
        else: # modo Manual
            if rele == True:
                pin_rele.value(1)
            else:
                pin_rele.value(0)

        await asyncio.sleep(1)

async def publicar_datos(id_dispositivo):
    while True:
        try:
            sensor.measure()
            t = sensor.temperature()
            h = sensor.humidity()

            parametros["temperatura"] = t
            parametros["humedad"] = h
            
            
            await client.publish(id_dispositivo, json.dumps(parametros), qos=0)
            print(f"Publicado -> {parametros}")
            
        except OSError:
            print("Error sensor")
        
        # await asyncio.sleep(parametros.get("periodo", 5)) 

#---------- Funcion Principal ----------
async def main(client):
    global ID_DISPOSITIVO
    ID_DISPOSITIVO = await obtener_id_mac()

    # parametros = await cargar_parametros()
    await guardar_parametros(parametros)

    setpoint = parametros["setpoint"]
    periodo = parametros["periodo"]
    modo = parametros["modo"]
    rele = parametros["rele"]

    print(f"\n   Estado actual de rele: {parametros["rele"]}")
    print(f"   Modo actual: {parametros["modo"]}\n")


    print("----------------------------------------------------")
    print(f"        MAC ID: [ {ID_DISPOSITIVO} ]")
    print(f"        Setpoint: {parametros['setpoint']} ")
    print(f"        Modo: {parametros['modo']}")
    print(f"        Periodo: {parametros['periodo']}")
    print(f"        Rele Estado: {parametros['rele']}")
    print("----------------------------------------------------")

    print("Intentando conectar al broker...")
    await client.connect()

    # Esperamos a que el evento 'up' de la librería se active
    while not client.isconnected(): 
        await asyncio.sleep(1)
    await asyncio.sleep(1)
    print("¡Conectado exitosamente!")

    evento_suscrito = asyncio.Event() #uso esto porque me molesta que empiece a medir sin que se haya subscrito, quedaba feo
    
    asyncio.create_task(up(client, evento_suscrito))
    asyncio.create_task(messages(client))
    asyncio.create_task(rele_modo(parametros))
    # asyncio.create_task(destello())

    print("Esperando suscripciones...")
    await evento_suscrito.wait() 
    print("\nSuscripciones listas. Iniciando sensado. \n\n")
    
    # asyncio.create_task(publicar_datos(ID_DISPOSITIVO))
    
    while True:
        while True:
            try:
                sensor.measure()
                t = sensor.temperature()
                h = sensor.humidity()

                parametros["temperatura"] = t
                parametros["humedad"] = h
                
                
                conversion_parametros=json.dumps(parametros)
                await client.publish(ID_DISPOSITIVO, conversion_parametros, qos=0)
                print(f"Publicado -> {conversion_parametros}")
                
            except OSError:
                print("Error sensor")
            
            await asyncio.sleep(parametros.get("periodo", 5)) 

#----------  Conexion con el cliente  #----------
config['ssl'] = True #para cifrar los datos
config["socket_timeout"] = 20
config["queue_len"] = 1  # Use event interface with default queue size
MQTTClient.DEBUG = False  # Optional: print diagnostic messages
client = MQTTClient(config)

try:
    asyncio.run(main(client))
finally:
    client.close()
    asyncio.new_event_loop()