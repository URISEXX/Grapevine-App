import streamlit as st
import pymongo
from datetime import datetime, timedelta
import pandas as pd
import time
import re # NUEVA LIBRERÍA: Nos ayudará a limpiar el HTML

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Grapevine Web", layout="wide", page_icon="🍇")

# --- CONEXIÓN A BASE DE DATOS ---
@st.cache_resource
def init_connection():
    # Pega tu link de MongoDB Atlas aquí:
    return pymongo.MongoClient("mongodb+srv://uriel_db:Macuca12.@cluster0.opwh0ou.mongodb.net/?appName=Cluster0")

try:
    client = init_connection()
    db = client["condominio_db"]
except Exception as e:
    st.error(f"Error conectando a la Base de Datos: {e}")
    st.stop()

# --- GESTIÓN DE SESIÓN ---
if 'usuario' not in st.session_state:
    st.session_state['usuario'] = None
if 'rol' not in st.session_state:
    st.session_state['rol'] = None

# ======================================================
# LÓGICA DE SEGURIDAD (SOC)
# ======================================================
def obtener_ip_real():
    """Atrapa la IP real buscando en cabeceras minúsculas y mayúsculas"""
    try:
        # Convertimos todas las cabeceras a minúsculas para evitar errores en la nube
        headers = {k.lower(): str(v) for k, v in st.context.headers.items()}
        ip_fallback = "127.0.0.1"
        
        # Buscamos en las 3 cabeceras más comunes de la nube
        for cabecera in ["x-forwarded-for", "x-real-ip", "client-ip"]:
            if cabecera in headers:
                lista_ips = headers[cabecera].split(",")
                for ip in lista_ips:
                    ip = ip.strip()
                    if ip:
                        ip_fallback = ip # Guarda la última encontrada por si acaso
                        # Si NO es privada/local, entonces es la pública que buscamos
                        if not ip.startswith(("10.", "172.", "192.168.", "127.", "::1")):
                            return ip 
        return f"{ip_fallback} (Proxy/Oculta)"
    except Exception:
        return "IP-No-Detectada"

def registrar_evento_soc(usuario_intentado, alerta):
    db["bitacora"].insert_one({
        "fecha_hora": datetime.now(),
        "ip": obtener_ip_real(),
        "usuario_intentado": usuario_intentado if usuario_intentado else "desconocido",
        "alerta": alerta
    })

def login(usuario, clave):
    user = db["usuarios"].find_one({"nombre": usuario})
    
    if user:
        if "bloqueado_hasta" in user and user["bloqueado_hasta"]:
            if datetime.now() < user["bloqueado_hasta"]:
                faltan = int((user["bloqueado_hasta"] - datetime.now()).total_seconds())
                if faltan > 0:
                    espacio_reloj = st.empty()
                    while faltan > 0:
                        espacio_reloj.error(f"⛔ Cuenta bloqueada por seguridad. Desbloqueo en: **{faltan} segundos**.")
                        time.sleep(1)
                        faltan -= 1
                    
                    espacio_reloj.success("✅ Cuenta desbloqueada. Ya puedes intentar de nuevo.")
                    time.sleep(1.5)
                    espacio_reloj.empty()
                    
                    db["usuarios"].update_one({"_id": user["_id"]}, {"$set": {"bloqueado_hasta": None, "intentos_fallidos": 0}})
                    st.rerun()
                return

        if user.get("clave") == clave:
            db["usuarios"].update_one({"_id": user["_id"]}, {"$set": {"intentos_fallidos": 0}})
            registrar_evento_soc(usuario, "INICIO DE SESIÓN EXITOSO")
            st.session_state['usuario'] = user
            st.session_state['rol'] = user.get("rol", "user")
            st.rerun()
        else:
            intentos = user.get("intentos_fallidos", 0) + 1
            if intentos >= 3:
                bloqueo = datetime.now() + timedelta(seconds=10)
                db["usuarios"].update_one({"_id": user["_id"]}, {"$set": {"intentos_fallidos": intentos, "bloqueado_hasta": bloqueo}})
                registrar_evento_soc(usuario, "USUARIO BLOQUEADO TEMPORALMENTE")
                st.error("⛔ Demasiados intentos fallidos. Tu cuenta ha sido bloqueada. Presiona 'Entrar' de nuevo para ver el reloj.")
            else:
                db["usuarios"].update_one({"_id": user["_id"]}, {"$set": {"intentos_fallidos": intentos}})
                registrar_evento_soc(usuario, "INTENTO DE INICIO DE SESIÓN FALLIDO")
                st.error(f"Contraseña incorrecta. Intento {intentos}/3")
    else:
        registrar_evento_soc(usuario, "INTENTO DE USUARIO INEXISTENTE")
        st.error("Usuario o contraseña incorrectos")

def logout():
    registrar_evento_soc(st.session_state['usuario']['nombre'], "CIERRE DE SESIÓN")
    st.session_state['usuario'] = None
    st.session_state['rol'] = None
    st.rerun()

# ======================================================
# VISTAS (FRONTEND)
# ======================================================

def mostrar_login():
    st.title("🍇 Acceso Grapevine")
    st.markdown("Sistema de Seguridad Digital para Fraccionamientos")
    
    usuario = st.text_input("Usuario")
    clave = st.text_input("Contraseña", type="password")
    
    if st.button("Entrar", type="primary", use_container_width=True):
        login(usuario, clave)

def vista_residente():
    u = st.session_state['usuario']
    st.sidebar.title(f"Hola, {u['nombre']} 👋")
    st.sidebar.write(f"🏠 Casa: {u.get('casa', 'S/N')}")
    if st.sidebar.button("Cerrar Sesión"):
        logout()

    tab1, tab2 = st.tabs(["💰 Mis Pagos", "🚨 Seguridad y Reportes"])

    with tab1:
        st.header("Estado de Cuenta")
        anio_sel = st.number_input("Selecciona el Año:", min_value=2020, max_value=2030, value=datetime.now().year)
        
        html_calendario = f"""
        <div style='background-color: #1E1E1E; padding: 20px; border-radius: 15px; box-shadow: 0 4px 10px rgba(0,0,0,0.5); max-width: 350px; margin: 10px auto; border: 1px solid #333;'>
        <h3 style='text-align: center; color: #FFFFFF; margin-top: 0; margin-bottom: 20px; font-family: sans-serif;'>Resumen {anio_sel}</h3>
        <div style='display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; text-align: center;'>
        """
        
        meses = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
        for i, mes in enumerate(meses):
            mes_num = i + 1
            pago = db["pagos"].find_one({"casa": u['casa'], "tipo": "Mantenimiento", "fecha": {"$regex": f"^{anio_sel}-{mes_num:02d}"}})
            estado = "🟢" if pago and pago['estado'] == 'Pagado' else ("🔴" if pago else "⚪")
            html_calendario += f"<div><div style='color: #A0A0A0; font-size: 15px; font-weight: bold; margin-bottom: 5px;'>{mes}</div><div style='font-size: 24px;'>{estado}</div></div>"
            
        html_calendario += "</div><div style='text-align: center; margin-top: 20px; font-size: 12px; color: #888;'>🟢 Pagado | 🔴 Pendiente | ⚪ Sin cargo</div></div>"
        
        # EL TRUCO DE MAGIA: Removemos saltos de línea y espacios extras para que Markdown no se confunda
        html_limpio = re.sub(r'\s+', ' ', html_calendario)
        st.markdown(html_limpio, unsafe_allow_html=True)
        st.divider()
        
        st.subheader(f"Historial Detallado ({anio_sel})")
        pagos = list(db["pagos"].find({"casa": u['casa']}).sort("fecha", -1))
        if pagos:
            df_pagos = pd.DataFrame(pagos)
            if 'tipo' not in df_pagos.columns: df_pagos['tipo'] = 'Mantenimiento'
            df_pagos = df_pagos.rename(columns={"fecha": "Fecha", "concepto": "Concepto", "monto": "$", "estado": "Estado"})

            with st.expander("📅 Cuotas de Mantenimiento", expanded=True):
                df_mto = df_pagos[df_pagos['tipo'] == 'Mantenimiento']
                if not df_mto.empty: st.table(df_mto[["Fecha", "Concepto", "$", "Estado"]].set_index("Fecha"))
        else:
            st.info("Aún no tienes historial de pagos.")

    with tab2:
        st.header("Línea Directa de Seguridad")
        numero_admin = "527220000000" # <--- CAMBIA ESTO POR TU NÚMERO
        mensaje = f"Hola Seguridad, soy {u['nombre']} de la casa {u.get('casa', 'S/N')}. Requiero asistencia para un reporte:"
        link_wa = f"https://wa.me/{numero_admin}?text={mensaje.replace(' ', '%20')}"
        st.link_button("🟢 Enviar WhatsApp a Seguridad", link_wa, use_container_width=True)

def vista_admin():
    st.sidebar.title("Panel Admin 🛡️")
    menu = st.sidebar.radio("Ir a:", ["Usuarios", "Pagos y Finanzas", "Centro SOC 🚨"])
    if st.sidebar.button("Cerrar Sesión"):
        logout()

    if menu == "Usuarios":
        st.title("Gestión de Residentes y Credenciales")
        # (Se mantiene igual tu tabla de usuarios)
        usuarios = list(db["usuarios"].find())
        if usuarios:
            df_users = pd.DataFrame(usuarios)[["nombre", "casa", "rol", "clave"]]
            df_users = df_users.rename(columns={"nombre": "Nombre", "casa": "Casa", "rol": "Rol", "clave": "Contraseña"})
            st.table(df_users.set_index("Nombre"))

    elif menu == "Pagos y Finanzas":
        st.title("Control Financiero")
        usuarios = list(db["usuarios"].find({"rol": "user"}))
        opciones = [f"{u['nombre']} | Casa: {u.get('casa')}" for u in usuarios]
        seleccion = st.selectbox("Seleccionar Residente:", opciones)
        
        if seleccion:
            nombre_user = seleccion.split(" | ")[0]
            usuario_actual = db["usuarios"].find_one({"nombre": nombre_user})
            st.divider()
            anio_sel = st.number_input("Año de Gestión:", min_value=2020, max_value=2030, value=datetime.now().year)

            st.markdown(f"### ⚙️ Gestionar Meses de {anio_sel}")
            meses = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
            
            # SOLUCIÓN CELULAR: Generamos filas cronológicas para que no salte de Ene a Abr en móviles
            for fila in range(4):
                cols = st.columns(3)
                for col in range(3):
                    idx = fila * 3 + col
                    mes_accion = meses[idx]
                    mes_num = idx + 1
                    pago_actual = db["pagos"].find_one({"usuario_id": usuario_actual["_id"], "tipo": "Mantenimiento", "fecha": {"$regex": f"^{anio_sel}-{mes_num:02d}"}})
                    
                    with cols[col]:
                        with st.container(border=True):
                            st.markdown(f"<div style='text-align: center; font-size: 15px;'><b>{mes_accion}</b></div>", unsafe_allow_html=True)
                            if pago_actual:
                                if pago_actual['estado'] == 'Pagado':
                                    st.button("✅ OK", key=f"btn_ok_{idx}", disabled=True, use_container_width=True)
                                else:
                                    if st.button("🔴 Cobrar", key=f"btn_pay_{idx}", use_container_width=True):
                                        db["pagos"].update_one({"_id": pago_actual["_id"]}, {"$set": {"estado": "Pagado", "fecha_pago": datetime.now().strftime("%Y-%m-%d")}})
                                        st.rerun()
                            else:
                                if st.button("⚪ Generar", key=f"btn_new_{idx}", use_container_width=True):
                                    db["pagos"].insert_one({"usuario_id": usuario_actual["_id"], "casa": usuario_actual.get("casa"), "nombre_usuario": usuario_actual.get("nombre"), "tipo": "Mantenimiento", "concepto": f"Mantenimiento {mes_accion} {anio_sel}", "monto": "500", "estado": "Pendiente", "fecha": f"{anio_sel}-{mes_num:02d}-01"})
                                    st.rerun()

    elif menu == "Centro SOC 🚨":
        st.title("🛡️ TASSFLOW SECURITY - SOC")
        st.markdown("<p style='color: #888;'>Reporte Ejecutivo de Seguridad del Sistema</p>", unsafe_allow_html=True)
        st.error("🛡️ **Estado del Sistema: PROTEGIDO**\n\nSistema operativo y monitoreando eventos de seguridad activamente.")
        
        eventos = list(db["bitacora"].find().sort("fecha_hora", -1))
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("TOTAL EVENTOS", f"{len(eventos)}")
        with col2:
            st.metric("ESTADO RED", "ACTIVO 🟢")
        with col3:
            if st.button("🗑️ Purgar Bitácora", help="Elimina todo el historial"):
                db["bitacora"].delete_many({})
                st.rerun()

        st.subheader("Registros de Seguridad Recientes")
        if eventos:
            df_eventos = pd.DataFrame(eventos)
            df_eventos["fecha_hora"] = df_eventos["fecha_hora"].dt.strftime("%d/%m/%Y %H:%M:%S")
            df_eventos = df_eventos[["fecha_hora", "ip", "usuario_intentado", "alerta"]]
            df_eventos = df_eventos.rename(columns={"fecha_hora": "FECHA Y HORA", "ip": "DIRECCIÓN IP", "usuario_intentado": "USUARIO INTENTADO", "alerta": "ALERTA"})
            st.dataframe(df_eventos, use_container_width=True, hide_index=True)
        else:
            st.info("Sin anomalías. El sistema está limpio.")

# ======================================================
# CONTROLADOR PRINCIPAL
# ======================================================
if st.session_state['usuario']:
    if st.session_state['rol'] == 'admin':
        vista_admin()
    else:
        vista_residente()
else:
    mostrar_login()
