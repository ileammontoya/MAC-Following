from seguimiento_macs import get_isla_ips
from netmiko import ConnectHandler
from netmiko import SSHDetect
import subprocess
import openpyxl
import re



def ping(host):
	'''	
		Funcion para probar ping hacia una ip
		Retorna True si el ping es exitoso
		Retorna False si el ping falla
	'''
	command = 'ping -n 1 {}'.format(host)
	return subprocess.call(command, stdout=subprocess.DEVNULL) == 0

def try_connection(router, ip):
	'''
		Funcion que utiliza Netmiko para conectarse a un equipo.
		Intenta detectar el tipo de equipo al que se va a conectar
		En caso de no poder averiguar el tipo de conexion SSH a realizar, se conectará bajo el modo de Cisco
		En caso de ser rechazada la conexion SSH, se intenta conectar a traves de Telnet
		En caso de conectar, retorna una conexion basada en Netmiko, de lo contrario retorna una lista vacia 
	'''
	conn=[]
	try:
		print('Detecting device type for ip '+ip)
		device = SSHDetect(**router).autodetect()
		if not device:
			device = 'cisco_ios'
		print('Trying SSH on ip {} of device type {}'.format(ip,device))
		router['device_type'] = device
		conn = ConnectHandler(**router)
	except Exception as e:
		print(e)
		try:
			print('Trying Telnet on ip '+ip)
			router['device_type'] = 'cisco_ios_telnet'
			conn = ConnectHandler(**router)
		except Exception as e:
			print(e)
			print('Unable to connect to ip '+ip+'\n\n')

	return conn

def find_cdp_huawei(cdp_list,writing,conn,hostname):
	'''
		Funcion que levanta los vecinos lldp y descripciones de las interfaces encontradas en equipos Huawei
		Se utiliza Regex para capturar los strings necesarios
		Resultados se guardan archivo de texto bajo el siguiente formato:
		Interface Gi0/0/0 Neighbor EQUIPO10
		Interface Gi0/0/0 Neighbor DESCRIPCION
	'''
	writing.write('\n\n--------------------------------------------------\n\n')
	print('PROCESSING NEIGHBORS FOR {} on {} interfaces'.format(hostname,len(cdp_list)))
	for interface in cdp_list:
		output = conn.send_command('display lldp nei interface {}'.format(interface))
		#Regex captura los siguientes ejemplos: 
		#System name                        :GNCYGTPAS1D3C01B03EIM2
		#SysName: GNCYGTDON1W1A01AA1YOM1 
		lldp_device = re.findall('Sys.*ame *:(.+)\n',output)
		if lldp_device:
			#El split('.')[0] separa el string en el punto y selecciona la seccion con el mnemonico del equipo
			writing.write('Interface {} - Neighbor {}\n'.format(interface,lldp_device[0].split('.')[0].strip()))
		else:
			output = conn.send_command('display int description {}'.format(interface))
			#Regex captura la descripcion, ejemplos:
			#GE0/2/3                     hacia 2G_3G_LTE_GO_FINCA LA PROVIDENCIA_(1882)
			#100GE7/0/0                    up      up       NNI_PE_MUL_10.179.28.24_100GE7/0/0_I_FO_HUAW_100G
			description = re.findall('(.+up +up|GE\d+\/\d+\/\d+)(.+)',output)
			if description:
				#El strip() quita cualquier espacio extra al principio y final del string
				writing.write('Interface {} - Neighbor {}\n'.format(interface,description[0][1].strip()))
			else:
				#En caso de no capturar lldp ni descripcion, se debe verificar la interfaz
				writing.write('Interface {} - Neighbor MUST BE VERIFIED\n'.format(interface))

def find_cdp_xr_ios(cdp_list,writing,conn,hostname):
	'''
		Funcion que levanta los vecinos cdp, lldp y descripciones encontradas en equipos Cisco
		Se utiliza Regex para capturar los strings necesarios
		Resultados se guardan archivo de texto bajo el siguiente formato:
		Interface Gi0/0/0 Neighbor EQUIPOx
		Interface Gi0/0/0 Neighbor DESCRIPCION
	'''
	writing.write('\n\n--------------------------------------------------\n\n')
	print('PROCESSING NEIGHBORS FOR {} on {} interfaces'.format(hostname,len(cdp_list)))
	for interface in cdp_list:
		output = conn.send_command('show cdp neighbor {} detail'.format(interface))
		#Regex captura el siguiente ejemplo: 
		#Device ID: GNCYGTSAN1C1101A01F8M2.claro.com.gt
		cdp_device = re.findall('Device ID: (.+)\n',output)
		if cdp_device:
			#El split('.')[0] separa el string en el punto y selecciona la seccion con el mnemonico del equipo
			writing.write('Interface {} - Neighbor {}\n'.format(interface,cdp_device[0].split('.')[0]))
		else: 
			output = conn.send_command('show lldp neighbor {} detail'.format(interface))
			#Regex captura el siguiente ejemplo: 
			#System Name: GNCYGTLON2D1D01A02EIM3
			lldp_device = re.findall('System Name: (.+)\n',output)
			if lldp_device:
				#El split('.')[0] separa el string en el punto y selecciona la seccion con el mnemonico del equipo
				writing.write('Interface {} - Neighbor {}\n'.format(interface,lldp_device[0].split('.')[0]))
			else:
				output = conn.send_command('show interface {} description'.format(interface))
				#Captura la descripcion de la interfaz si esta se encuentra arriba
				#eg. Gi0/0/20                       up             up       hacia MSAN CENTRA NORTE - GNCYGTE0N1C1A01A06COA0 (10.102.135.69)
				description = re.findall('.+up +up +(.+)',output)
				if description:
					writing.write('Interface {} - Neighbor {}\n'.format(interface,description[0]))
				else:
					#En caso de no capturar cdp, lldp ni descripcion, se debe verificar la interfaz
					writing.write('Interface {} - Neighbor MUST BE VERIFIED\n'.format(interface))

def recopila(ip):
	"""	
		Conecta a un equipo y levanta tabla de macs junto con los cdp/lldp neighbor
		Guarda info en archivos de texto especificando hostname e ip
		Los resultados se escriben en archivos de texto individuales con el siguiente formato de nombre y contenido:
		Nombre: EQUIPO - IP.txt
		MAC-ADDRESS	INTERFACE
		--------------------------------------------------
		Interface Fa0/24 - Neighbor EQUIPOx
	"""
	cdp_list=[]
	data_path = 'C:/Users/Ileam Montoya/Dropbox/PYTHON/Python Scripts/CLARO/Seguimiento Macs/Levantamiento/data/{} - {}.txt'
	if ping(ip):
		user_pass= '/Users/Ileam Montoya/Dropbox/Claro/Automatization/password_claro_actual/authentication.txt'
		with open(user_pass) as file:
			username = file.readline().strip('\n')
			password = file.readline()
		router = {
		    'ip': ip,
		    'username': username,
		    'password': password,
		    'device_type': 'autodetect'
			}
		conn = try_connection(router, ip)
		if conn:
			try:
				prompt = conn.find_prompt()
				#Se verifica el prompt y en caso de contener > es un equipo Huawei
				if '>' in prompt:
					#En caso de que se haya conectado un equipo huawei en modo cisco
					if router['device_type'] == 'cisco_ios':
						conn.disconnect()
						router['device_type'] = 'huawei'
						try:
							conn = ConnectHandler(**router)
						except:
							print('Error en Huawei')
					print('HUAWEI '+prompt)
					hostname=re.sub('[<>]', '', prompt)
					output = conn.send_command('display mac-address')
					#Regex captura la mac e interfaz de salida en un Huawei, ejemplo:
					#1409-dcf4-92fb 1666        -      -      GE6/0/0         dynamic   4/-         
					mac_ints=re.findall('(....-....-....) \d+ +-      - +(.+) +dynamic',output)
					writing=open(data_path.format(hostname,ip),'w')
					for i, j in mac_ints:
						#Por ser Huawei, se cambie el GE por Gi excepto cuando la interfaz es 100GE
						#En las macs se cambia el - por .
						k=j.replace('GE','Gi') if '100' not in j else j
						writing.write('{}\t{}\n'.format(i.replace('-','.'),k))
						if k not in cdp_list:
							cdp_list.append(k)
					find_cdp_huawei(cdp_list,writing,conn,hostname)
					writing.close()
				#Se verifica el prompt y en caso de contener : es un equipo XR
				elif ':' in prompt:
					print('XR '+prompt)
					hostname=re.findall('RP/0/RSP0/CPU0:(.+)#',prompt)[0]
					#El levantamiento de macs en XR depende del dominio del equipo y la vlan, se debe modificar el comando antes de correr el script
					print('EJECUTANDO COMANDO SOBRE EQUIPO XR - VERIFICAR COMANDO DE DOMINIO Y VLAN')
					output = conn.send_command('show l2vpn forwarding bridge-domain L2TRUNKS:VLAN3579 mac-address location 0/0/CPU0 ')
					mac_ints=re.findall('(....\.....\.....) dynamic (.+) +0/0/CPU0',output)
					writing=open(data_path.format(hostname,ip),'w')
					for i, j in mac_ints:
						neighbor_int = j.split('.')[0]
						writing.write('{}\t{}\n'.format(i,neighbor_int))
						if neighbor_int not in cdp_list:
							cdp_list.append(neighbor_int)
					find_cdp_xr_ios(cdp_list,writing,conn,hostname)
					writing.close()
				#Si no es Huawei ni XR se califica como IOS
				else:
					print('IOS '+prompt)
					hostname=re.findall('(.+)#',prompt)[0]
					version = conn.send_command('show version')
					output = conn.send_command('show mac-address-table')
					#En caso de que el equipo rechace el comando show mac-address-table se lanza el siguiente:
					#show mac address-table
					if 'Invalid input' in output:
						print('DIFFERENT MAC COMMAND FOR IP {}'.format(ip))
						output = conn.send_command('show mac address-table')
					#Dentro de IOS cada version lanza lineas un poco diferentes en su tabla mac
					#En esta seccion se separan las versiones y se realizan las capturas necesarias
					if 'ASR-920' in version:
						mac_ints=re.findall('(....\.....\.....)  DYNAMIC  (.+) +',output)
						writing=open(data_path.format(hostname,ip),'w')
						for i, j in mac_ints:
							neighbor_int = j.split('.')[0]
							if 'Po' in neighbor_int:
								neighbor_int = 'Po'+re.findall('\d+$',neighbor_int)[0]
							writing.write('{}\t{}\n'.format(i,neighbor_int))
							if neighbor_int not in cdp_list:
								cdp_list.append(neighbor_int)
						find_cdp_xr_ios(cdp_list,writing,conn,hostname)
						writing.close()
					elif 'ME-3' in version or 'ME-C3' in version:
						mac_ints=re.findall('(....\.....\.....)    DYNAMIC     (.+)\n',output)
						writing=open(data_path.format(hostname,ip),'w')
						for i, j in mac_ints:
							writing.write('{}\t{}\n'.format(i,j))
							if j not in cdp_list:
								cdp_list.append(j)
						find_cdp_xr_ios(cdp_list,writing,conn,hostname)
						writing.close()
					elif ' CISCO76' in version:
						mac_ints=re.findall('(....\.....\.....).+\d+ +(.+)\n',output)
						writing=open(data_path.format(hostname,ip),'w')
						for i, j in mac_ints:
							writing.write('{}\t{}\n'.format(i,j))
							if j not in cdp_list:
								cdp_list.append(j)
						find_cdp_xr_ios(cdp_list,writing,conn,hostname)
						writing.close()
	#Se capturan errores en el levantamiento, conexion o ping
			except Exception as e:
				writing=open(data_path.format('ERROR LEVANTAMIENTO',ip),'w')
				writing.close()
				print('ERROR DURANTE LEVANTAMIENTO DE EQUIPO {}'.format(ip))
				writing=open(data_path.format('LOG','ERRORES'),'a')
				writing.write('ERROR DURANTE LEVANTAMIENTO DE EQUIPO {}\n'.format(ip))
				writing.write(str(e)+'\n\n\n')
				writing.close()	
			conn.disconnect()
		else:
			writing=open(data_path.format('ERROR CONEXION',ip),'w')
			writing.close()
			print('NO HAY CONEXION AL EQUIPO DE IP {}'.format(ip))
			writing=open(data_path.format('LOG','ERRORES'),'a')
			writing.write('NO HAY CONEXION AL EQUIPO DE IP {}\n\n\n'.format(ip))
			writing.close()	

	else:
		writing=open(data_path.format('ERROR PING',ip),'w')
		writing.close()
		print('ERROR PING - {}'.format(ip))
		writing=open(data_path.format('LOG','ERRORES'),'a')
		writing.write('ERROR PING - {}\n\n\n'.format(ip))
		writing.close()	

if __name__ == "__main__":

	#Carga archivo excel y las pestañas necesarias
	path_excel = 'C:/Users/Ileam Montoya/Dropbox/PYTHON/Python Scripts/CLARO/Seguimiento Macs/Levantamiento/informacion_macs.xlsx'
	informacion_macs = openpyxl.load_workbook(path_excel)
	equipos_isla = informacion_macs['Equipos Isla']

	lista_equipos = get_isla_ips(equipos_isla)
	# lista_equipos=['10.78.18.5','10.179.20.11']

	for ip in lista_equipos:
		recopila(ip)