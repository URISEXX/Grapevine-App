import streamlit as st
import pymongo
from datetime import datetime
import pandas as pd

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Grapevine Web", layout="wide", page_icon="🍇")

# --- CONEXIÓN A BASE DE DATOS ---
@st.cache_resource
def init_connection():
    # OJO: Asegúrate de pegar AQUÍ tu link real de MongoDB Atlas
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
# FUNCIONES DE LÓGICA
# ======================================================
def login(usuario, clave):
    user = db["usuarios"].find_one({"nombre": usuario, "clave": clave})
    if user:
        st.session_state['usuario'] = user
        st.session_state['rol'] = user.get("rol", "user")
        st.rerun()
    else:
        st.error("Usuario o contraseña incorrectos")

def logout():
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
        
    if db["usuarios"].count_documents({}) == 0:
        if st.button("Crear Admin Inicial"):
            db["usuarios"].insert_one({"nombre":"admin", "clave":"1234", "rol":"admin", "casa":"Oficina"})
            st.success("Creado: admin / 1234")

def vista_residente():
    u = st.session_state['usuario']
    st.sidebar.title(f"Hola, {u['nombre']} 👋")
    st.sidebar.write(f"🏠 Casa: {u.get('casa', 'S/N')}")
    if st.sidebar.button("Cerrar Sesión"):
        logout()

    tab1, tab2 = st.tabs(["💰 Mis Pagos", "📢 Reportes"])

    with tab1:
        st.header("Estado de Cuenta")
        
        # --- CALENDARIO VISUAL COMPACTO (TIPO XIAOMI) ---
        st.subheader("Resumen Anual")
        
        anio_sel = st.number_input("Año:", min_value=2020, max_value=2030, value=datetime.now().year)
        st.info("🟢 Pagado | 🔴 Pendiente | ⚪ Sin cargo")

        meses = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
        
        # MINI CALENDARIO FORZADO EN HTML (No se rompe en celulares)
        html_grid = '<div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; text-align: center; margin-bottom: 20px;">'
        
        for i, mes in enumerate(meses):
            mes_num = i + 1
            patron = f"^{anio_sel}-{mes_num:02d}"
            
            pago = db["pagos"].find_one({
                "casa": u['casa'], 
                "tipo": "Mantenimiento", 
                "fecha": {"$regex": patron}
            })
            
            estado = "⚪"
            if pago:
                estado = "🟢" if pago['estado'] == 'Pagado' else "🔴"
            
            # Tarjetas de cada mes
            html_grid += f"""
            <div style="border: 1px solid rgba(128,128,128,0.3); border-radius: 8px; padding: 12px 5px; background-color: rgba(128,128,128,0.05);">
                <div style="font-size: 15px; font-weight: bold; margin-bottom: 5px;">{mes}</div>
                <div style="font-size: 20px;">{estado}</div>
            </div>
            """
            
        html_grid += '</div>'
        st.markdown(html_grid, unsafe_allow_html=True) # Renderiza el grid

        st.divider()
        
        # --- HISTORIAL (VERSIÓN TABLA COMPACTA) ---
        st.subheader(f"Historial Detallado ({anio_sel})")
        
        pagos = list(db["pagos"].find({"casa": u['casa']}).sort("fecha", -1))
        
        if pagos:
            df_pagos = pd.DataFrame(pagos)
            if 'tipo' not in df_pagos.columns: 
                df_pagos['tipo'] = 'Mantenimiento'

            df_pagos = df_pagos.rename(columns={"fecha": "Fecha", "concepto": "Concepto", "monto": "$", "estado": "Estado"})

            df_mto = df_pagos[df_pagos['tipo'] == 'Mantenimiento']
            df_extra = df_pagos[df_pagos['tipo'] == 'Extra']
            df_multa = df_pagos[df_pagos['tipo'] == 'Multa']

            with st.expander("📅 Cuotas de Mantenimiento", expanded=True):
                if not df_mto.empty:
                    st.table(df_mto[["Fecha", "Concepto", "$", "Estado"]].set_index("Fecha"))
                else:
                    st.caption("No hay registros de mantenimiento.")

            with st.expander("➕ Cargos Extra (Tarjetas, Reservas, etc.)"):
                if not df_extra.empty:
                    st.table(df_extra[["Fecha", "Concepto", "$", "Estado"]].set_index("Fecha"))
                else:
                    st.caption("No tienes cargos extra.")

            with st.expander("⚠️ Multas e Infracciones"):
                if not df_multa.empty:
                    st.table(df_multa[["Fecha", "Concepto", "$", "Estado"]].set_index("Fecha"))
                else:
                    st.success("¡Felicidades! No tienes multas registradas.")
        else:
            st.info("Aún no tienes historial de pagos.")

    with tab2:
        st.header("Generar Reporte")
        desc = st.text_area("Describe el problema:")
        if st.button("Enviar Reporte"):
            if desc:
                db["reportes"].insert_one({
                    "usuario": u["nombre"],
                    "casa": u["casa"],
                    "descripcion": desc,
                    "estado": "Pendiente",
                    "fecha": datetime.now().strftime("%Y-%m-%d")
                })
                st.success("Reporte enviado correctamente")
                st.rerun()
        
        st.subheader("Mis Reportes Anteriores")
        reportes = list(db["reportes"].find({"casa": u['casa']}).sort("fecha", -1))
        if reportes:
            df_rep = pd.DataFrame(reportes)
            df_rep = df_rep.rename(columns={"fecha": "Fecha", "descripcion": "Descripción", "estado": "Estado"})
            st.table(df_rep[["Fecha", "Descripción", "Estado"]].set_index("Fecha"))

def vista_admin():
    st.sidebar.title("Panel Admin 🛡️")
    menu = st.sidebar.radio("Ir a:", ["Usuarios", "Pagos y Finanzas", "Reportes"])
    if st.sidebar.button("Cerrar Sesión"):
        logout()

    if menu == "Usuarios":
        st.title("Gestión de Residentes")
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
                        db["usuarios"].insert_one({"nombre":n, "casa":c, "clave":p, "rol":r})
                        st.success("Guardado")
                        st.rerun()
        
        usuarios = list(db["usuarios"].find())
        if usuarios:
            st.dataframe(pd.DataFrame(usuarios)[["nombre", "casa", "rol"]], use_container_width=True)

    elif menu == "Pagos y Finanzas":
        st.title("Control Financiero Visual")
        
        usuarios = list(db["usuarios"].find({"rol": "user"}))
        opciones = [f"{u['nombre']} | Casa: {u.get('casa')}" for u in usuarios]
        seleccion = st.selectbox("Seleccionar Residente:", opciones)
        
        if seleccion:
            nombre_user = seleccion.split(" | ")[0]
            usuario_actual = db["usuarios"].find_one({"nombre": nombre_user})
            st.divider()
            
            anio_sel = st.number_input("Año de Gestión:", min_value=2020, max_value=2030, value=datetime.now().year)
            st.info("Clic en **Gris** para crear deuda. Clic en **Rojo** para cobrar.")

            st.subheader(f"Calendario {anio_sel}")
            meses = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
            
            # CORRECCIÓN ADMIN: Dibuja fila por fila para que en celular el orden sea Ene, Feb, Mar...
            for fila in range(4): # 4 filas
                cols = st.columns(3) # 3 columnas
                for col in range(3):
                    idx = fila * 3 + col
                    mes = meses[idx]
                    mes_num = idx + 1
                    patron = f"^{anio_sel}-{mes_num:02d}"
                    pago = db["pagos"].find_one({
                        "usuario_id": usuario_actual["_id"],
                        "tipo": "Mantenimiento",
                        "fecha": {"$regex": patron}
                    })

                    with cols[col]:
                        with st.container(border=True):
                            st.markdown(f"**{mes}**")
                            if pago:
                                if pago['estado'] == 'Pagado':
                                    st.button("✅ OK", key=f"btn_ok_{idx}", disabled=True, use_container_width=True)
                                else:
                                    if st.button("🔴 Cobrar", key=f"btn_pay_{idx}", use_container_width=True):
                                        db["pagos"].update_one({"_id": pago["_id"]}, {"$set": {"estado": "Pagado", "fecha_pago": datetime.now().strftime("%Y-%m-%d")}})
                                        st.toast(f"Pago de {mes} registrado!")
                                        st.rerun()
                            else:
                                if st.button("⚪ Generar", key=f"btn_new_{idx}", use_container_width=True):
                                    fecha_construida = f"{anio_sel}-{mes_num:02d}-01"
                                    db["pagos"].insert_one({
                                        "usuario_id": usuario_actual["_id"], "casa": usuario_actual.get("casa"), "nombre_usuario": usuario_actual.get("nombre"),
                                        "tipo": "Mantenimiento", "concepto": f"Mantenimiento {mes} {anio_sel}", "monto": "500", 
                                        "estado": "Pendiente", "fecha": fecha_construida
                                    })
                                    st.toast(f"Cargo de {mes} generado.")
                                    st.rerun()

            st.divider()
            
            st.subheader("Cargos Extra y Multas")
            with st.expander("Agregar Multa o Extra"):
                with st.form("form_extra"):
                    c_concepto = st.text_input("Concepto (ej. Multa Ruido)")
                    c_monto = st.text_input("Monto ($)", value="200")
                    c_tipo = st.selectbox("Tipo", ["Multa", "Extra"])
                    c_fecha = st.date_input("Fecha de Cargo", value=datetime.now())
                    
                    if st.form_submit_button("Registrar"):
                        db["pagos"].insert_one({
                            "usuario_id": usuario_actual["_id"], "casa": usuario_actual.get("casa"), 
                            "tipo": c_tipo, "concepto": c_concepto, "monto": c_monto,
                            "estado": "Pendiente", "fecha": c_fecha.strftime("%Y-%m-%d")
                        })
                        st.success("Registrado")
                        st.rerun()
            
            extras = list(db["pagos"].find({
                "usuario_id": usuario_actual["_id"], 
                "tipo": {"$ne": "Mantenimiento"} 
            }))
            if extras:
                for ex in extras:
                    with st.container(border=True):
                        st.write(f"**{ex['tipo']}**: {ex['concepto']} (${ex['monto']})")
                        st.caption(f"Fecha: {ex['fecha']} | Estado: {ex['estado']}")
                        if ex['estado'] == 'Pendiente':
                            if st.button("Cobrar", key=f"pay_ex_{ex['_id']}", use_container_width=True):
                                db["pagos"].update_one({"_id": ex["_id"]}, {"$set": {"estado": "Pagado"}})
                                st.rerun()

    elif menu == "Reportes":
        st.title("Bandeja de Quejas")
        reportes = list(db["reportes"].find().sort("fecha", -1))
        
        for r in reportes:
            with st.expander(f"{r['fecha']} - {r['usuario']} (Casa {r['casa']}) - {r['estado']}"):
                st.write(r['descripcion'])
                if r['estado'] == "Pendiente":
                    if st.button("✅ Atender y Eliminar", key=f"del_{r['_id']}", use_container_width=True):
                        db["reportes"].delete_one({"_id": r["_id"]})
                        st.success("Reporte cerrado")
                        st.rerun()

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

