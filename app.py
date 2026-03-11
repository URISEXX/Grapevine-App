import streamlit as st
import pymongo
from datetime import datetime, timedelta
import pandas as pd
import time
import re
import requests
import pydeck as pdk

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
# LÓGICA DE SEGURIDAD (SOC Y MAPAS)
# ======================================================

def hora_mexico():
    """Corrige el desfase de la nube para que coincida con el horario de México (UTC-6)"""
    return datetime.utcnow() - timedelta(hours=6)

def obtener_ip_real():
    try:
        headers = st.context.headers
        ip_header = headers.get("X-Forwarded-For") or headers.get("x-forwarded-for")
        if ip_header:
            return ip_header.split(",")[0].strip()
        return "127.0.0.1 (Local)"
    except Exception:
        return "IP-No-Detectada"

def obtener_datos_geo(ip):
    try:
        if ip.startswith(("10.", "172.", "192.168.", "127.", "::1")) or "Local" in ip or "Proxy" in ip:
            return None, None, "Red Local / Privada"
            
        respuesta = requests.get(f"https://get.geojs.io/v1/ip/geo/{ip}.json", timeout=3)
        if respuesta.status_code == 200:
            datos = respuesta.json()
            ciudad = datos.get("city", "Desconocida")
            pais = datos.get("country", "")
            ubicacion = f"{ciudad}, {pais}".strip(", ")
            return float(datos["latitude"]), float(datos["longitude"]), ubicacion
    except Exception:
        pass
    return None, None, "Ubicación Desconocida"

def registrar_evento_soc(usuario_intentado, alerta):
    ip_real = obtener_ip_real()
    lat, lon, ubicacion = obtener_datos_geo(ip_real)
    
    db["bitacora"].insert_one({
        "fecha_hora": hora_mexico(),
        "ip": ip_real,
        "usuario_intentado": usuario_intentado if usuario_intentado else "desconocido",
        "alerta": alerta,
        "lat": lat,
        "lon": lon,
        "ubicacion": ubicacion
    })

def login(usuario, clave):
    user = db["usuarios"].find_one({"nombre": usuario})
    
    if user:
        if "bloqueado_hasta" in user and user["bloqueado_hasta"]:
            if hora_mexico() < user["bloqueado_hasta"]:
                faltan = int((user["bloqueado_hasta"] - hora_mexico()).total_seconds())
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

        if user.get("sesion_activa") == True:
            st.error("⚠️ ALERTA: Esta cuenta ya está abierta en otro dispositivo.")
            registrar_evento_soc(usuario, "INTENTO DE DOBLE SESIÓN (POSIBLE CLONACIÓN)")
            return

        if user.get("clave") == clave:
            db["usuarios"].update_one({"_id": user["_id"]}, {"$set": {"intentos_fallidos": 0, "sesion_activa": True}})
            registrar_evento_soc(usuario, "INICIO DE SESIÓN EXITOSO")
            st.session_state['usuario'] = user
            st.session_state['rol'] = user.get("rol", "user")
            st.rerun()
        else:
            intentos = user.get("intentos_fallidos", 0) + 1
            if intentos >= 3:
                bloqueo = hora_mexico() + timedelta(seconds=10)
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
    db["usuarios"].update_one({"_id": st.session_state['usuario']['_id']}, {"$set": {"sesion_activa": False}})
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

    st.divider()
    with st.expander("🔌 ¿Tu sesión se quedó abierta en otro equipo?"):
        st.caption("Ingresa tus datos para forzar el cierre remoto.")
        u_desbloqueo = st.text_input("Usuario a desbloquear")
        p_desbloqueo = st.text_input("Contraseña", type="password", key="pass_desbloqueo")
        if st.button("Forzar Cierre Remoto", use_container_width=True):
            user_check = db["usuarios"].find_one({"nombre": u_desbloqueo, "clave": p_desbloqueo})
            if user_check:
                db["usuarios"].update_one({"_id": user_check["_id"]}, {"$set": {"sesion_activa": False}})
                registrar_evento_soc(u_desbloqueo, "FORZADO DE CIERRE REMOTO (EMERGENCIA)")
                st.success("✅ Sesión cerrada remotamente. Ya puedes entrar arriba.")
            else:
                st.error("Datos incorrectos.")

def vista_residente():
    u = st.session_state['usuario']
    st.sidebar.title(f"Hola, {u['nombre']} 👋")
    st.sidebar.write(f"🏠 Casa: {u.get('casa', 'S/N')}")
    if st.sidebar.button("Cerrar Sesión"):
        logout()

    tab1, tab2 = st.tabs(["💰 Mis Pagos", "🚨 Seguridad y Reportes"])

    with tab1:
        st.header("Estado de Cuenta")
        anio_sel = st.number_input("Selecciona el Año:", min_value=2020, max_value=2030, value=hora_mexico().year)
        
        html_calendario = f"""<div style='background-color: #1E1E1E; padding: 20px; border-radius: 15px; box-shadow: 0 4px 10px rgba(0,0,0,0.5); max-width: 350px; margin: 10px auto; border: 1px solid #333;'>
<h3 style='text-align: center; color: #FFFFFF; margin-top: 0; margin-bottom: 20px; font-family: sans-serif;'>Resumen {anio_sel}</h3>
<div style='display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; text-align: center;'>"""
        meses = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
        for i, mes in enumerate(meses):
            mes_num = i + 1
            pago = db["pagos"].find_one({"casa": u['casa'], "tipo": "Mantenimiento", "fecha": {"$regex": f"^{anio_sel}-{mes_num:02d}"}})
            estado = "🟢" if pago and pago['estado'] == 'Pagado' else ("🔴" if pago else "⚪")
            html_calendario += f"<div><div style='color: #A0A0A0; font-size: 15px; font-weight: bold; margin-bottom: 5px;'>{mes}</div><div style='font-size: 24px;'>{estado}</div></div>"
            
        html_calendario += "</div><div style='text-align: center; margin-top: 20px; font-size: 12px; color: #888;'>🟢 Pagado | 🔴 Pendiente | ⚪ Sin cargo</div></div>"
        
        st.markdown(re.sub(r'\n\s*', '', html_calendario), unsafe_allow_html=True)
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
                
            with st.expander("➕ Cargos Extra y Multas"):
                df_extra = df_pagos[df_pagos['tipo'] != 'Mantenimiento']
                if not df_extra.empty: st.table(df_extra[["Fecha", "Concepto", "$", "Estado"]].set_index("Fecha"))
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
        with st.expander("➕ Registrar Nuevo Vecino"):
            with st.form("nuevo_user"):
                n = st.text_input("Nombre")
                c = st.text_input("Casa")
                p = st.text_input("Contraseña")
                r = st.selectbox("Rol", ["user", "admin"])
                if st.form_submit_button("Guardar"):
                    if db["usuarios"].find_one({"nombre": n}):
                        st.error("Usuario ya existe")
                    else:
                        db["usuarios"].insert_one({"nombre":n, "casa":c, "clave":p, "rol":r, "intentos_fallidos": 0, "sesion_activa": False})
                        st.success("Guardado")
                        st.rerun()

        usuarios = list(db["usuarios"].find())
        if usuarios:
            df_users = pd.DataFrame(usuarios)[["nombre", "casa", "rol", "clave", "sesion_activa"]]
            df_users["sesion_activa"] = df_users["sesion_activa"].apply(lambda x: "🟢 En línea" if x else "⚪ Offline")
            df_users = df_users.rename(columns={"nombre": "Nombre", "casa": "Casa", "rol": "Rol", "clave": "Contraseña", "sesion_activa": "Estatus"})
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
            anio_sel = st.number_input("Año de Gestión:", min_value=2020, max_value=2030, value=hora_mexico().year)

            html_calendario = f"""<div style='background-color: #1E1E1E; padding: 20px; border-radius: 15px; box-shadow: 0 4px 10px rgba(0,0,0,0.5); max-width: 350px; margin: 10px auto; border: 1px solid #333;'>
<h3 style='text-align: center; color: #FFFFFF; margin-top: 0; margin-bottom: 20px; font-family: sans-serif;'>Resumen {anio_sel}</h3>
<div style='display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; text-align: center;'>"""
            
            meses = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
            pagos_del_anio = {}
            for i, mes in enumerate(meses):
                mes_num = i + 1
                pago = db["pagos"].find_one({"usuario_id": usuario_actual["_id"], "tipo": "Mantenimiento", "fecha": {"$regex": f"^{anio_sel}-{mes_num:02d}"}})
                pagos_del_anio[mes] = pago 
                estado = "🟢" if pago and pago['estado'] == 'Pagado' else ("🔴" if pago else "⚪")
                html_calendario += f"<div><div style='color: #A0A0A0; font-size: 15px; font-weight: bold; margin-bottom: 5px;'>{mes}</div><div style='font-size: 24px;'>{estado}</div></div>"
                
            html_calendario += "</div></div>"
            st.markdown(re.sub(r'\n\s*', '', html_calendario), unsafe_allow_html=True)
            st.divider()

            st.markdown("### ⚙️ Gestionar Mes")
            mes_accion = st.selectbox("Mes a gestionar:", meses)
            pago_actual = pagos_del_anio[mes_accion]
            mes_idx = meses.index(mes_accion) + 1

            if pago_actual:
                if pago_actual['estado'] == 'Pagado':
                    st.success(f"✅ El mes de {mes_accion} ya está pagado.")
                else:
                    st.warning(f"🔴 El mes de {mes_accion} tiene deuda pendiente.")
                    if st.button(f"Cobrar {mes_accion}", use_container_width=True, type="primary"):
                        db["pagos"].update_one({"_id": pago_actual["_id"]}, {"$set": {"estado": "Pagado", "fecha_pago": hora_mexico().strftime("%Y-%m-%d")}})
                        st.rerun()
            else:
                st.info(f"⚪ No hay cargo generado para {mes_accion}.")
                if st.button(f"Generar Cargo de {mes_accion}", use_container_width=True):
                    db["pagos"].insert_one({
                        "usuario_id": usuario_actual["_id"], "casa": usuario_actual.get("casa"), "nombre_usuario": usuario_actual.get("nombre"), 
                        "tipo": "Mantenimiento", "concepto": f"Mantenimiento {mes_accion} {anio_sel}", "monto": "500", "estado": "Pendiente", "fecha": f"{anio_sel}-{mes_idx:02d}-01"
                    })
                    st.rerun()

            st.divider()
            
            with st.expander("➕ Agregar Multa o Extra"):
                with st.form("form_extra"):
                    c_concepto = st.text_input("Concepto (ej. Multa Ruido)")
                    c_monto = st.text_input("Monto ($)", value="200")
                    c_tipo = st.selectbox("Tipo", ["Multa", "Extra"])
                    c_fecha = st.date_input("Fecha de Cargo", value=hora_mexico())
                    if st.form_submit_button("Registrar"):
                        db["pagos"].insert_one({
                            "usuario_id": usuario_actual["_id"], "casa": usuario_actual.get("casa"), "tipo": c_tipo, "concepto": c_concepto, 
                            "monto": c_monto, "estado": "Pendiente", "fecha": c_fecha.strftime("%Y-%m-%d")
                        })
                        st.rerun()
            
            extras = list(db["pagos"].find({"usuario_id": usuario_actual["_id"], "tipo": {"$ne": "Mantenimiento"}}))
            if extras:
                for ex in extras:
                    with st.container(border=True):
                        st.write(f"**{ex['tipo']}**: {ex['concepto']} (${ex['monto']})")
                        if ex['estado'] == 'Pendiente':
                            if st.button("Cobrar Cargo", key=f"pay_ex_{ex['_id']}", use_container_width=True):
                                db["pagos"].update_one({"_id": ex["_id"]}, {"$set": {"estado": "Pagado"}})
                                st.rerun()

    elif menu == "Centro SOC 🚨":
        st.title("🛡️ TASSFLOW SECURITY - SOC")
        st.markdown("<p style='color: #888;'>Reporte Ejecutivo de Seguridad y Rastreo Geográfico</p>", unsafe_allow_html=True)
        st.error("🛡️ **Estado del Sistema: PROTEGIDO**\n\nSistema Anti-Clonación activado. Rastreo de red activo.")
        
        eventos = list(db["bitacora"].find().sort("fecha_hora", -1))
        
        ataques_clonacion = [e for e in eventos if "CLONACIÓN" in str(e.get("alerta", ""))]
        if ataques_clonacion:
            st.warning("⚠️ **ALERTA DE SEGURIDAD:** Se han detectado intentos de clonación de sesión. Revisa la tabla inferior y el mapa.")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("TOTAL EVENTOS", f"{len(eventos)}")
        with col2:
            st.metric("ESTADO RED", "ACTIVO 🟢")
        with col3:
            if st.button("🗑️ Purgar Bitácora", help="Elimina todo el historial"):
                db["bitacora"].delete_many({})
                st.rerun()

        # --- MAPA DE RASTREO LIMPIO (SÓLO PUNTITOS) ---
        st.subheader("🌍 Mapa de Rastreo de Conexiones Reales")
        eventos_con_geo = [e for e in eventos if e.get("lat") is not None and e.get("lon") is not None]
        
        if eventos_con_geo:
            mapa_data = []
            for e in eventos_con_geo:
                mapa_data.append({
                    "lat": e.get("lat"), 
                    "lon": e.get("lon"), 
                    "lugar": f"IP: {e.get('ip')} ({e.get('ubicacion', 'Desconocida')})"
                })
            
            df_mapa = pd.DataFrame(mapa_data)
            lat_centro = df_mapa.iloc[0]["lat"]
            lon_centro = df_mapa.iloc[0]["lon"]
            
            capa_puntos = pdk.Layer(
                "ScatterplotLayer",
                data=df_mapa,
                get_position="[lon, lat]",
                get_fill_color="[255, 50, 50, 200]", # Color rojo fijo y serio
                get_radius=1500, # Punto chiquito y preciso
                pickable=True
            )
            vista_inicial = pdk.ViewState(latitude=lat_centro, longitude=lon_centro, zoom=10, pitch=45)
            
            st.pydeck_chart(pdk.Deck(
                map_style=None, 
                layers=[capa_puntos], # Se quitó la capa de texto (letras en el mapa)
                initial_view_state=vista_inicial,
                tooltip={"html": "<b>📍 {lugar}</b>"}
            ))
        else:
            st.info("Aún no hay suficientes datos públicos para generar el mapa. (Las IPs locales no se muestran).")

        st.divider()

        # --- TABLA DE REGISTROS LIMPIA ---
        st.subheader("Registros de Seguridad Recientes")
        if eventos:
            eventos_formateados = []
            for e in eventos:
                eventos_formateados.append({
                    "FECHA Y HORA": e["fecha_hora"].strftime("%d/%m/%Y %H:%M:%S"),
                    "DIRECCIÓN IP": e.get("ip", "Desconocida"), # Sin emojis
                    "UBICACIÓN": e.get("ubicacion", "Desconocida"),
                    "USUARIO INTENTADO": e.get("usuario_intentado", "desconocido"),
                    "ALERTA": e.get("alerta", "")
                })
                
            df_eventos = pd.DataFrame(eventos_formateados)
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
