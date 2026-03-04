import json
import random
import pygame

# --- LÓGICA DE AGENTES SOTL ---
class SemaforoSOTL:
    def __init__(self, id_nodo, x, y):
        self.id_nodo = id_nodo
        self.x = x
        self.y = y
        self.estado = 'ROJO'
        self.vehiculos_esperando = 0
        self.tiempo_en_estado = 0
        self.umbral_theta = 50
        self.tiempo_verde_max = 3000  # ms máximo en verde

    def actualizar(self, dt):
        self.tiempo_en_estado += dt
        if self.estado == 'ROJO':
            kappa = self.vehiculos_esperando * self.tiempo_en_estado
            if kappa >= self.umbral_theta:
                self.cambiar_fase()
        else:
            # Volver a rojo después de un tiempo o si no hay vehículos esperando
            if self.tiempo_en_estado >= self.tiempo_verde_max:
                self.cambiar_fase()

    def cambiar_fase(self):
        self.estado = 'VERDE' if self.estado == 'ROJO' else 'ROJO'
        self.tiempo_en_estado = 0

# --- ENTORNO Y GRAFO ---
class Calle:
    def __init__(self, origen, destino, capacidad):
        self.origen = origen
        self.destino = destino
        self.capacidad = capacidad
        self.vehiculos = []  # lista de floats 0.0 a 1.0 (progreso en la calle)
        self.accidente_activo = False

class SimulacionSOTL:
    def __init__(self, archivo_red):
        self.nodos = {}
        self.calles = []
        self.calles_por_destino = {}  # nodo_id -> [calles que llegan]
        self.calles_por_origen = {}   # nodo_id -> [calles que salen]
        self.cargar_red(archivo_red)

        # Parámetros estocásticos
        self.probabilidad_accidente_p = 0.02
        self.intervalo_accidente_t = 2000
        self.tiempo_acumulado_accidente = 0

        # Generación de vehículos
        self.intervalo_spawn = 200  # ms entre spawns
        self.tiempo_acumulado_spawn = 0

    def cargar_red(self, archivo):
        with open(archivo, 'r') as f:
            data = json.load(f)

        for nodo_data in data['nodos']:
            nid = nodo_data['id']
            self.nodos[nid] = SemaforoSOTL(nid, nodo_data['x'], nodo_data['y'])

        for calle_data in data['calles']:
            origen = self.nodos[calle_data['origen']]
            destino = self.nodos[calle_data['destino']]
            capacidad = calle_data['capacidad']
            calle = Calle(origen, destino, capacidad)
            self.calles.append(calle)

            oid = calle_data['origen']
            did = calle_data['destino']
            self.calles_por_origen.setdefault(oid, []).append(calle)
            self.calles_por_destino.setdefault(did, []).append(calle)

    def generar_vehiculos(self, dt):
        self.tiempo_acumulado_spawn += dt
        if self.tiempo_acumulado_spawn >= self.intervalo_spawn:
            self.tiempo_acumulado_spawn = 0
            # Inyectar vehículos en calles aleatorias que no estén llenas
            calles_disponibles = [c for c in self.calles if len(c.vehiculos) < c.capacidad]
            if calles_disponibles:
                calle = random.choice(calles_disponibles)
                calle.vehiculos.append(0.0)

    def mover_vehiculos(self, dt):
        velocidad = dt / 2000.0  # velocidad base normalizada

        for calle in self.calles:
            if not calle.vehiculos:
                continue

            cap_efectiva = calle.capacidad * (0.3 if calle.accidente_activo else 1.0)
            vel = velocidad * (cap_efectiva / calle.capacidad)

            nuevos = []
            for progreso in calle.vehiculos:
                progreso += vel
                if progreso >= 1.0:
                    # Vehículo llega al destino: si semáforo verde, pasa; si rojo, espera
                    if calle.destino.estado == 'VERDE':
                        # Redirigir a otra calle saliente del nodo destino
                        salidas = self.calles_por_origen.get(calle.destino.id_nodo, [])
                        salidas_ok = [s for s in salidas if len(s.vehiculos) < s.capacidad and s.destino != calle.origen]
                        if salidas_ok:
                            siguiente = random.choice(salidas_ok)
                            siguiente.vehiculos.append(0.0)
                        # Vehículo sale de esta calle
                    else:
                        # Espera al final de la calle
                        nuevos.append(min(progreso, 0.99))
                else:
                    nuevos.append(progreso)
            calle.vehiculos = nuevos

    def contar_vehiculos_esperando(self):
        # Resetear contadores
        for nodo in self.nodos.values():
            nodo.vehiculos_esperando = 0

        for calle in self.calles:
            # Contar vehículos cerca del final (>= 0.8 de progreso)
            esperando = sum(1 for v in calle.vehiculos if v >= 0.8)
            calle.destino.vehiculos_esperando += esperando

    def inyectar_accidentes(self, dt):
        self.tiempo_acumulado_accidente += dt
        if self.tiempo_acumulado_accidente >= self.intervalo_accidente_t:
            self.tiempo_acumulado_accidente = 0
            # Limpiar accidentes anteriores con probabilidad
            for calle in self.calles:
                if calle.accidente_activo and random.random() < 0.3:
                    calle.accidente_activo = False
            # Nuevo accidente
            if random.random() < self.probabilidad_accidente_p:
                calle_afectada = random.choice(self.calles)
                calle_afectada.accidente_activo = True

    def step(self, dt):
        self.generar_vehiculos(dt)
        self.mover_vehiculos(dt)
        self.contar_vehiculos_esperando()
        self.inyectar_accidentes(dt)
        for nodo in self.nodos.values():
            nodo.actualizar(dt)

# --- RENDERIZADO VISUAL ---
def ejecutar_visualizacion():
    pygame.init()
    pantalla = pygame.display.set_mode((800, 650))
    pygame.display.set_caption("Simulación Net Interactions - SOTL")
    reloj = pygame.time.Clock()
    fuente = pygame.font.SysFont(None, 18)

    sim = SimulacionSOTL("data/interactions.json")

    corriendo = True
    while corriendo:
        dt = reloj.tick(60)

        for evento in pygame.event.get():
            if evento.type == pygame.QUIT:
                corriendo = False

        sim.step(dt)

        pantalla.fill((30, 30, 30))

        # Dibujar calles
        for calle in sim.calles:
            color = (180, 50, 50) if calle.accidente_activo else (70, 70, 70)
            pygame.draw.line(pantalla, color,
                             (calle.origen.x, calle.origen.y),
                             (calle.destino.x, calle.destino.y), 2)

            # Dibujar vehículos como puntos amarillos
            for progreso in calle.vehiculos:
                vx = calle.origen.x + (calle.destino.x - calle.origen.x) * progreso
                vy = calle.origen.y + (calle.destino.y - calle.origen.y) * progreso
                pygame.draw.circle(pantalla, (255, 220, 50), (int(vx), int(vy)), 3)

        # Dibujar nodos (semáforos)
        for nodo in sim.nodos.values():
            color = (0, 220, 0) if nodo.estado == 'VERDE' else (220, 0, 0)
            pygame.draw.circle(pantalla, color, (nodo.x, nodo.y), 12)
            pygame.draw.circle(pantalla, (255, 255, 255), (nodo.x, nodo.y), 12, 1)
            etiqueta = fuente.render(nodo.id_nodo, True, (255, 255, 255))
            pantalla.blit(etiqueta, (nodo.x - etiqueta.get_width() // 2, nodo.y - 25))

        pygame.display.flip()

    pygame.quit()

if __name__ == "__main__":
    ejecutar_visualizacion()