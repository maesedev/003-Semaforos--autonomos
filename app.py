import argparse
import json
import math
import os
import random
import time
from datetime import datetime

import pygame


# --- TRACKING Y MÉTRICAS ---

class Vehiculo:
    _counter = 0

    def __init__(self, calle, tiempo_actual):
        Vehiculo._counter += 1
        self.id = Vehiculo._counter
        self.progreso = 0.0
        self.calle_actual = calle
        self.tiempo_spawn = tiempo_actual
        self.tiempo_inicio_espera = None  # cuando empezó a esperar en rojo
        self.tiempos_espera = []          # lista de ms esperados en cada semáforo
        self.nodos_cruzados = []          # historial de nodos atravesados
        self.esperando = False


class Tracker:
    """Recolecta métricas detalladas de la simulación."""
    def __init__(self):
        self.vehiculos_totales = 0
        self.vehiculos_completados = 0  # salieron de la red
        self.cambios_fase = []           # {tiempo, nodo, fase_anterior, fase_nueva, kappa, esperando}
        self.accidentes = []             # {tiempo, calle}
        self.snapshots = []              # estado periódico del sistema
        self.esperas_por_vehiculo = {}   # vid -> [tiempos de espera]
        self.max_cola_por_nodo = {}      # nodo_id -> max vehículos antes de cambio
        self.vehiculos_por_nodo = {}     # nodo_id -> lista de conteos al cambiar fase
        self.tiempo_simulacion = 0
        self.snapshot_interval = 500     # ms entre snapshots
        self.tiempo_ultimo_snapshot = 0
        self.fases_por_nodo = {}         # nodo_id -> [fase_activa en cada snapshot]

    def registrar_cambio_fase(self, tiempo, nodo, fase_ant, fase_nueva, kappa, esperando):
        self.cambios_fase.append({
            "tiempo_ms": round(tiempo),
            "nodo": nodo.id_nodo,
            "fase_anterior": fase_ant,
            "fase_nueva": fase_nueva,
            "kappa_acumulado": round(kappa, 2),
            "vehiculos_esperando": esperando
        })
        # Registrar cola máxima
        nid = nodo.id_nodo
        if nid not in self.max_cola_por_nodo:
            self.max_cola_por_nodo[nid] = 0
        self.max_cola_por_nodo[nid] = max(self.max_cola_por_nodo[nid], esperando)
        self.vehiculos_por_nodo.setdefault(nid, []).append(esperando)

    def registrar_accidente(self, tiempo, calle):
        self.accidentes.append({
            "tiempo_ms": round(tiempo),
            "calle": f"{calle.origen.id_nodo}->{calle.destino.id_nodo}"
        })

    def registrar_espera(self, vehiculo_id, tiempo_espera):
        self.esperas_por_vehiculo.setdefault(vehiculo_id, []).append(round(tiempo_espera))

    def tomar_snapshot(self, tiempo, sim):
        if tiempo - self.tiempo_ultimo_snapshot < self.snapshot_interval:
            return
        self.tiempo_ultimo_snapshot = tiempo

        total_vehiculos = sum(len(c.vehiculos_obj) for c in sim.calles)
        vehiculos_esperando = 0
        for c in sim.calles:
            vehiculos_esperando += sum(1 for v in c.vehiculos_obj if v.esperando)

        fases_activas = {}
        for nid, nodo in sim.nodos.items():
            if len(nodo.fases) > 1:
                fases_activas[nid] = nodo.fase_activa
                self.fases_por_nodo.setdefault(nid, []).append(nodo.fase_activa)

        self.snapshots.append({
            "tiempo_ms": round(tiempo),
            "vehiculos_en_red": total_vehiculos,
            "vehiculos_esperando": vehiculos_esperando,
            "fases_activas": fases_activas
        })

    def generar_reporte(self, sim):
        # Análisis de esperas
        todas_esperas = []
        for vid, esperas in self.esperas_por_vehiculo.items():
            todas_esperas.extend(esperas)

        espera_min = min(todas_esperas) if todas_esperas else 0
        espera_max = max(todas_esperas) if todas_esperas else 0
        espera_promedio = sum(todas_esperas) / len(todas_esperas) if todas_esperas else 0

        # Análisis de convergencia de fases
        convergencia = self._analizar_convergencia()

        # Análisis de cambios de fase por nodo
        cambios_por_nodo = {}
        for cambio in self.cambios_fase:
            nid = cambio["nodo"]
            cambios_por_nodo[nid] = cambios_por_nodo.get(nid, 0) + 1

        # Distribución de tiempos entre cambios por nodo
        tiempos_entre_cambios = self._tiempos_entre_cambios()

        # Estadísticas por nodo
        stats_nodos = {}
        for nid, nodo in sorted(sim.nodos.items()):
            n_cambios = cambios_por_nodo.get(nid, 0)
            max_cola = self.max_cola_por_nodo.get(nid, 0)
            colas = self.vehiculos_por_nodo.get(nid, [])
            cola_promedio = sum(colas) / len(colas) if colas else 0
            t_entre = tiempos_entre_cambios.get(nid, [])
            stats_nodos[nid] = {
                "total_cambios_fase": n_cambios,
                "max_vehiculos_en_cola": max_cola,
                "promedio_vehiculos_en_cola": round(cola_promedio, 2),
                "tiempo_entre_cambios_min_ms": min(t_entre) if t_entre else 0,
                "tiempo_entre_cambios_max_ms": max(t_entre) if t_entre else 0,
                "tiempo_entre_cambios_promedio_ms": round(sum(t_entre) / len(t_entre)) if t_entre else 0
            }

        reporte = {
            "metadata": {
                "fecha": datetime.now().isoformat(),
                "tiempo_simulacion_ms": round(self.tiempo_simulacion),
                "tiempo_simulacion_seg": round(self.tiempo_simulacion / 1000, 2),
                "total_nodos": len(sim.nodos),
                "total_calles": len(sim.calles)
            },
            "vehiculos": {
                "total_generados": self.vehiculos_totales,
                "total_completados": self.vehiculos_completados,
                "en_red_al_finalizar": self.vehiculos_totales - self.vehiculos_completados
            },
            "esperas": {
                "min_ms": espera_min,
                "max_ms": espera_max,
                "promedio_ms": round(espera_promedio, 2),
                "total_eventos_espera": len(todas_esperas),
                "distribucion_percentiles": self._percentiles(todas_esperas)
            },
            "semaforos": {
                "total_cambios_fase": len(self.cambios_fase),
                "convergencia": convergencia,
                "estadisticas_por_nodo": stats_nodos
            },
            "accidentes": {
                "total": len(self.accidentes),
                "detalle": self.accidentes[:50]  # primeros 50
            },
            "serie_temporal": self.snapshots,
            "cambios_fase_detalle": self.cambios_fase[:200]  # primeros 200
        }
        return reporte

    def _analizar_convergencia(self):
        """Evalúa si los semáforos convergieron a un estado estático o mantuvieron dinamismo."""
        if not self.fases_por_nodo:
            return {"estado": "sin_datos"}

        # Para cada nodo, ver si la fase cambió en el último tercio de snapshots
        resultados = {}
        convergidos = 0
        total = 0
        for nid, fases in self.fases_por_nodo.items():
            if len(fases) < 6:
                continue
            total += 1
            tercio = len(fases) // 3
            ultimo_tercio = fases[-tercio:]
            valores_unicos = len(set(ultimo_tercio))
            if valores_unicos == 1:
                convergidos += 1
                resultados[nid] = "convergido"
            else:
                cambios = sum(1 for i in range(1, len(ultimo_tercio)) if ultimo_tercio[i] != ultimo_tercio[i-1])
                resultados[nid] = f"dinamico ({cambios} cambios en ultimo tercio)"

        ratio = convergidos / total if total > 0 else 0
        if ratio > 0.7:
            estado = "CONVERGENCIA_ALTA - La mayoría de semáforos se estancaron en una fase"
        elif ratio > 0.3:
            estado = "CONVERGENCIA_PARCIAL - Algunos semáforos se estancaron"
        else:
            estado = "DINAMICO - Los semáforos mantienen alternancia saludable"

        return {
            "estado_general": estado,
            "ratio_convergidos": round(ratio, 3),
            "nodos_convergidos": convergidos,
            "nodos_dinamicos": total - convergidos,
            "detalle_por_nodo": resultados
        }

    def _tiempos_entre_cambios(self):
        """Calcula tiempos entre cambios de fase consecutivos por nodo."""
        cambios_por_nodo = {}
        for c in self.cambios_fase:
            cambios_por_nodo.setdefault(c["nodo"], []).append(c["tiempo_ms"])

        resultado = {}
        for nid, tiempos in cambios_por_nodo.items():
            if len(tiempos) < 2:
                continue
            deltas = [tiempos[i] - tiempos[i-1] for i in range(1, len(tiempos))]
            resultado[nid] = deltas
        return resultado

    def _percentiles(self, datos):
        if not datos:
            return {}
        s = sorted(datos)
        n = len(s)
        return {
            "p10": s[int(n * 0.1)],
            "p25": s[int(n * 0.25)],
            "p50": s[int(n * 0.5)],
            "p75": s[int(n * 0.75)],
            "p90": s[min(int(n * 0.9), n - 1)],
            "p99": s[min(int(n * 0.99), n - 1)]
        }


# --- LÓGICA DE AGENTES SOTL CON FASES CONFLICTIVAS ---

class FaseSemaforo:
    """Agrupa calles compatibles que pueden tener verde simultáneamente."""
    def __init__(self, indice):
        self.indice = indice
        self.calles = []
        self.kappa = 0.0

    def vehiculos_esperando(self):
        total = 0
        for calle in self.calles:
            total += sum(1 for v in calle.vehiculos_obj if v.esperando or v.progreso >= 0.8)
        return total


class SemaforoSOTL:
    """Gestor de fases conflictivas en una intersección."""
    def __init__(self, id_nodo, x, y):
        self.id_nodo = id_nodo
        self.x = x
        self.y = y
        self.fases = []
        self.fase_activa = 0
        self.tiempo_en_fase = 0
        self.umbral_theta = 800
        self.tiempo_verde_min = 1500
        self.tiempo_verde_max = 5000
        self.tracker = None  # se asigna después

    def construir_fases(self, calles_entrantes):
        if not calles_entrantes:
            return

        calles_con_angulo = []
        for calle in calles_entrantes:
            dx = calle.origen.x - self.x
            dy = calle.origen.y - self.y
            angulo = math.atan2(dy, dx)
            calles_con_angulo.append((angulo, calle))

        fase_h = FaseSemaforo(0)
        fase_v = FaseSemaforo(1)

        for angulo, calle in calles_con_angulo:
            grados = math.degrees(angulo) % 360
            if (grados < 45 or grados > 315 or (135 < grados < 225)):
                fase_h.calles.append(calle)
            else:
                fase_v.calles.append(calle)

        if fase_h.calles:
            self.fases.append(fase_h)
        if fase_v.calles:
            self.fases.append(fase_v)

        if not self.fases and calles_con_angulo:
            unica = FaseSemaforo(0)
            unica.calles = [c for _, c in calles_con_angulo]
            self.fases.append(unica)

    def calle_tiene_verde(self, calle):
        if not self.fases:
            return False
        return calle in self.fases[self.fase_activa].calles

    def actualizar(self, dt, tiempo_global):
        if len(self.fases) <= 1:
            return

        self.tiempo_en_fase += dt

        for i, fase in enumerate(self.fases):
            if i != self.fase_activa:
                esperando = fase.vehiculos_esperando()
                fase.kappa += esperando * dt

        if self.tiempo_en_fase >= self.tiempo_verde_min:
            max_kappa = 0
            mejor_fase = self.fase_activa
            for i, fase in enumerate(self.fases):
                if i != self.fase_activa and fase.kappa > max_kappa:
                    max_kappa = fase.kappa
                    mejor_fase = i

            if max_kappa >= self.umbral_theta or self.tiempo_en_fase >= self.tiempo_verde_max:
                if mejor_fase != self.fase_activa:
                    fase_ant = self.fase_activa
                    esperando = self.fases[mejor_fase].vehiculos_esperando()

                    if self.tracker:
                        self.tracker.registrar_cambio_fase(
                            tiempo_global, self, fase_ant, mejor_fase,
                            max_kappa, esperando
                        )

                    self.fases[mejor_fase].kappa = 0
                    self.fase_activa = mejor_fase
                    self.tiempo_en_fase = 0


# --- ENTORNO Y GRAFO ---

class Calle:
    def __init__(self, origen, destino, capacidad):
        self.origen = origen
        self.destino = destino
        self.capacidad = capacidad
        self.vehiculos_obj = []  # lista de Vehiculo
        self.accidente_activo = False

    @property
    def vehiculos(self):
        """Compatibilidad: retorna lista de progresos."""
        return [v.progreso for v in self.vehiculos_obj]


class SimulacionSOTL:
    def __init__(self, archivo_red, tracker=None):
        self.nodos = {}
        self.calles = []
        self.calles_por_destino = {}
        self.calles_por_origen = {}
        self.tracker = tracker
        self.tiempo_global = 0
        self.cargar_red(archivo_red)
        self.construir_fases_nodos()

        self.probabilidad_accidente_p = 0.02
        self.intervalo_accidente_t = 2000
        self.tiempo_acumulado_accidente = 0
        self.intervalo_spawn = 200
        self.tiempo_acumulado_spawn = 0

    def cargar_red(self, archivo):
        with open(archivo, 'r') as f:
            data = json.load(f)

        for nodo_data in data['nodos']:
            nid = nodo_data['id']
            nodo = SemaforoSOTL(nid, nodo_data['x'], nodo_data['y'])
            nodo.tracker = self.tracker
            self.nodos[nid] = nodo

        for calle_data in data['calles']:
            origen = self.nodos[calle_data['origen']]
            destino = self.nodos[calle_data['destino']]
            capacidad = calle_data['capacidad']
            calle = Calle(origen, destino, capacidad)
            self.calles.append(calle)
            self.calles_por_origen.setdefault(calle_data['origen'], []).append(calle)
            self.calles_por_destino.setdefault(calle_data['destino'], []).append(calle)

    def construir_fases_nodos(self):
        for nid, nodo in self.nodos.items():
            entrantes = self.calles_por_destino.get(nid, [])
            nodo.construir_fases(entrantes)
            if nodo.fases and len(nodo.fases) > 1:
                nodo.fase_activa = random.randint(0, len(nodo.fases) - 1)
                nodo.tiempo_en_fase = random.randint(0, 2000)

    def generar_vehiculos(self, dt):
        self.tiempo_acumulado_spawn += dt
        if self.tiempo_acumulado_spawn >= self.intervalo_spawn:
            self.tiempo_acumulado_spawn = 0
            calles_disponibles = [c for c in self.calles if len(c.vehiculos_obj) < c.capacidad]
            if calles_disponibles:
                calle = random.choice(calles_disponibles)
                v = Vehiculo(calle, self.tiempo_global)
                calle.vehiculos_obj.append(v)
                if self.tracker:
                    self.tracker.vehiculos_totales += 1
                return v
        return None

    def mover_vehiculos(self, dt):
        velocidad = dt / 2000.0

        for calle in self.calles:
            if not calle.vehiculos_obj:
                continue

            factor = 0.3 if calle.accidente_activo else 1.0
            vel = velocidad * factor

            nuevos = []
            for v in calle.vehiculos_obj:
                v.progreso += vel
                if v.progreso >= 1.0:
                    tiene_verde = calle.destino.calle_tiene_verde(calle)
                    if tiene_verde:
                        # Si estaba esperando, registrar tiempo de espera
                        if v.esperando and v.tiempo_inicio_espera is not None:
                            t_espera = self.tiempo_global - v.tiempo_inicio_espera
                            v.tiempos_espera.append(t_espera)
                            if self.tracker:
                                self.tracker.registrar_espera(v.id, t_espera)
                            v.esperando = False
                            v.tiempo_inicio_espera = None

                        v.nodos_cruzados.append(calle.destino.id_nodo)

                        # Redirigir
                        salidas = self.calles_por_origen.get(calle.destino.id_nodo, [])
                        salidas_ok = [s for s in salidas
                                      if len(s.vehiculos_obj) < s.capacidad
                                      and s.destino != calle.origen]
                        if salidas_ok:
                            siguiente = random.choice(salidas_ok)
                            v.progreso = 0.0
                            v.calle_actual = siguiente
                            siguiente.vehiculos_obj.append(v)
                        else:
                            # Sin salida: vehículo sale de la red
                            if self.tracker:
                                self.tracker.vehiculos_completados += 1
                    else:
                        # Rojo: espera
                        v.progreso = min(v.progreso, 0.99)
                        if not v.esperando:
                            v.esperando = True
                            v.tiempo_inicio_espera = self.tiempo_global
                        nuevos.append(v)
                else:
                    nuevos.append(v)
            calle.vehiculos_obj = nuevos

    def inyectar_accidentes(self, dt):
        self.tiempo_acumulado_accidente += dt
        if self.tiempo_acumulado_accidente >= self.intervalo_accidente_t:
            self.tiempo_acumulado_accidente = 0
            for calle in self.calles:
                if calle.accidente_activo and random.random() < 0.3:
                    calle.accidente_activo = False
            if random.random() < self.probabilidad_accidente_p:
                calle_afectada = random.choice(self.calles)
                calle_afectada.accidente_activo = True
                if self.tracker:
                    self.tracker.registrar_accidente(self.tiempo_global, calle_afectada)

    def total_vehiculos(self):
        return sum(len(c.vehiculos_obj) for c in self.calles)

    def step(self, dt):
        self.tiempo_global += dt
        self.generar_vehiculos(dt)
        self.mover_vehiculos(dt)
        self.inyectar_accidentes(dt)
        for nodo in self.nodos.values():
            nodo.actualizar(dt, self.tiempo_global)
        if self.tracker:
            self.tracker.tiempo_simulacion = self.tiempo_global
            self.tracker.tomar_snapshot(self.tiempo_global, self)


# --- RENDERIZADO VISUAL ---

def ejecutar_visualizacion(track_limit=None):
    pygame.init()
    pantalla = pygame.display.set_mode((800, 650))
    pygame.display.set_caption("Simulación Net Interactions - SOTL")
    reloj = pygame.time.Clock()
    fuente = pygame.font.SysFont(None, 16)
    fuente_info = pygame.font.SysFont(None, 14)

    tracker = Tracker() if track_limit else None
    sim = SimulacionSOTL("data/interactions.json", tracker=tracker)

    corriendo = True
    while corriendo:
        dt = reloj.tick(60)

        for evento in pygame.event.get():
            if evento.type == pygame.QUIT:
                corriendo = False

        sim.step(dt)

        # Verificar límite de tracking
        if track_limit and tracker and tracker.vehiculos_totales >= track_limit:
            print(f"\n--- Límite de {track_limit} vehículos alcanzado. Generando reporte... ---\n")
            guardar_reporte(tracker, sim)
            corriendo = False
            continue

        pantalla.fill((30, 30, 30))

        # Dibujar calles
        for calle in sim.calles:
            tiene_verde = calle.destino.calle_tiene_verde(calle)
            if calle.accidente_activo:
                color = (180, 50, 50)
            elif tiene_verde:
                color = (50, 100, 50)
            else:
                color = (60, 60, 60)
            pygame.draw.line(pantalla, color,
                             (calle.origen.x, calle.origen.y),
                             (calle.destino.x, calle.destino.y), 2)

            for v in calle.vehiculos_obj:
                vx = calle.origen.x + (calle.destino.x - calle.origen.x) * v.progreso
                vy = calle.origen.y + (calle.destino.y - calle.origen.y) * v.progreso
                vc = (255, 160, 30) if v.esperando else (255, 220, 50)
                pygame.draw.circle(pantalla, vc, (int(vx), int(vy)), 3)

        # Dibujar nodos
        for nodo in sim.nodos.values():
            if len(nodo.fases) <= 1:
                pygame.draw.circle(pantalla, (0, 180, 0), (nodo.x, nodo.y), 10)
            else:
                fase_h_activa = nodo.fase_activa == 0
                color_h = (0, 200, 0) if fase_h_activa else (200, 0, 0)
                color_v = (200, 0, 0) if fase_h_activa else (0, 200, 0)
                pygame.draw.circle(pantalla, color_h, (nodo.x - 5, nodo.y), 7)
                pygame.draw.circle(pantalla, color_v, (nodo.x + 5, nodo.y), 7)

            pygame.draw.circle(pantalla, (255, 255, 255), (nodo.x, nodo.y), 11, 1)
            etiqueta = fuente.render(nodo.id_nodo, True, (220, 220, 220))
            pantalla.blit(etiqueta, (nodo.x - etiqueta.get_width() // 2, nodo.y - 22))

        # Info bar
        total_v = sim.total_vehiculos()
        info_text = f"Vehículos en red: {total_v}  |  Nodos: {len(sim.nodos)}"
        if tracker:
            info_text += f"  |  Generados: {tracker.vehiculos_totales}/{track_limit}"
            info_text += f"  |  Completados: {tracker.vehiculos_completados}"
        info = fuente_info.render(info_text, True, (150, 150, 150))
        pantalla.blit(info, (10, 635))

        pygame.display.flip()

    pygame.quit()


def guardar_reporte(tracker, sim):
    os.makedirs("results", exist_ok=True)
    reporte = tracker.generar_reporte(sim)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"results/reporte_{timestamp}.json"
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(reporte, f, indent=2, ensure_ascii=False)
    print(f"Reporte guardado en: {filename}")

    # Resumen en consola
    r = reporte
    print(f"\n{'='*60}")
    print(f"  RESUMEN DE SIMULACIÓN SOTL")
    print(f"{'='*60}")
    print(f"  Duración: {r['metadata']['tiempo_simulacion_seg']}s")
    print(f"  Vehículos generados: {r['vehiculos']['total_generados']}")
    print(f"  Vehículos completados: {r['vehiculos']['total_completados']}")
    print(f"  Espera mínima: {r['esperas']['min_ms']}ms")
    print(f"  Espera máxima: {r['esperas']['max_ms']}ms")
    print(f"  Espera promedio: {r['esperas']['promedio_ms']}ms")
    print(f"  Cambios de fase totales: {r['semaforos']['total_cambios_fase']}")
    print(f"  Accidentes: {r['accidentes']['total']}")
    conv = r['semaforos']['convergencia']
    if 'estado_general' in conv:
        print(f"  Convergencia: {conv['estado_general']}")
        print(f"  Ratio convergidos: {conv['ratio_convergidos']}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulación SOTL de semáforos")
    parser.add_argument("--track", type=int, default=None,
                        help="Cantidad de vehículos a generar antes de detener y generar reporte")
    args = parser.parse_args()
    ejecutar_visualizacion(track_limit=args.track)
