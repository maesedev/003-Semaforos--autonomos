import json
import math
import random
import pygame


# --- LÓGICA DE AGENTES SOTL CON FASES CONFLICTIVAS ---

class FaseSemaforo:
    """Agrupa calles compatibles que pueden tener verde simultáneamente."""
    def __init__(self, indice):
        self.indice = indice
        self.calles = []  # calles entrantes asignadas a esta fase
        self.kappa = 0.0  # presión acumulada SOTL

    def vehiculos_esperando(self):
        total = 0
        for calle in self.calles:
            total += sum(1 for v in calle.vehiculos if v >= 0.8)
        return total


class SemaforoSOTL:
    """Gestor de fases conflictivas en una intersección."""
    def __init__(self, id_nodo, x, y):
        self.id_nodo = id_nodo
        self.x = x
        self.y = y
        self.fases = []          # lista de FaseSemaforo
        self.fase_activa = 0     # índice de la fase con verde
        self.tiempo_en_fase = 0
        self.umbral_theta = 800  # umbral SOTL para cambio de fase
        self.tiempo_verde_min = 1500   # ms mínimo en verde
        self.tiempo_verde_max = 5000   # ms máximo en verde

    def construir_fases(self, calles_entrantes):
        """Clasifica calles entrantes en fases por ángulo de llegada."""
        if not calles_entrantes:
            return

        # Calcular ángulo de cada calle entrante respecto al nodo
        calles_con_angulo = []
        for calle in calles_entrantes:
            dx = calle.origen.x - self.x
            dy = calle.origen.y - self.y
            angulo = math.atan2(dy, dx)  # radianes
            calles_con_angulo.append((angulo, calle))

        # Agrupar en 2 fases: ángulos opuestos son compatibles
        # Fase 0: calles ~horizontales, Fase 1: calles ~verticales/diagonales
        fase_h = FaseSemaforo(0)
        fase_v = FaseSemaforo(1)

        for angulo, calle in calles_con_angulo:
            grados = math.degrees(angulo) % 360
            # Horizontal: 0°±45° o 180°±45°
            if (grados < 45 or grados > 315 or (135 < grados < 225)):
                fase_h.calles.append(calle)
            else:
                fase_v.calles.append(calle)

        # Solo agregar fases que tengan calles
        if fase_h.calles:
            self.fases.append(fase_h)
        if fase_v.calles:
            self.fases.append(fase_v)

        # Si solo hay una fase (calles en una sola dirección), agregarla
        if not self.fases and calles_con_angulo:
            unica = FaseSemaforo(0)
            unica.calles = [c for _, c in calles_con_angulo]
            self.fases.append(unica)

    def calle_tiene_verde(self, calle):
        """Retorna True si la calle pertenece a la fase activa."""
        if not self.fases:
            return False
        fase = self.fases[self.fase_activa]
        return calle in fase.calles

    def actualizar(self, dt):
        if len(self.fases) <= 1:
            # Con una sola fase o ninguna, siempre verde
            return

        self.tiempo_en_fase += dt
        fase_actual = self.fases[self.fase_activa]

        # Acumular kappa en las fases EN ROJO (las que esperan)
        for i, fase in enumerate(self.fases):
            if i != self.fase_activa:
                esperando = fase.vehiculos_esperando()
                fase.kappa += esperando * dt

        # Evaluar cambio de fase
        if self.tiempo_en_fase >= self.tiempo_verde_min:
            # Buscar la fase con mayor presión
            max_kappa = 0
            mejor_fase = self.fase_activa
            for i, fase in enumerate(self.fases):
                if i != self.fase_activa and fase.kappa > max_kappa:
                    max_kappa = fase.kappa
                    mejor_fase = i

            # Cambiar si la presión supera el umbral o se agotó el verde máximo
            if max_kappa >= self.umbral_theta or self.tiempo_en_fase >= self.tiempo_verde_max:
                if mejor_fase != self.fase_activa:
                    # Reset kappa de la fase que entra
                    self.fases[mejor_fase].kappa = 0
                    self.fase_activa = mejor_fase
                    self.tiempo_en_fase = 0


# --- ENTORNO Y GRAFO ---

class Calle:
    def __init__(self, origen, destino, capacidad):
        self.origen = origen
        self.destino = destino
        self.capacidad = capacidad
        self.vehiculos = []  # floats 0.0 a 1.0 (progreso)
        self.accidente_activo = False


class SimulacionSOTL:
    def __init__(self, archivo_red):
        self.nodos = {}
        self.calles = []
        self.calles_por_destino = {}
        self.calles_por_origen = {}
        self.cargar_red(archivo_red)
        self.construir_fases_nodos()

        # Parámetros estocásticos
        self.probabilidad_accidente_p = 0.02
        self.intervalo_accidente_t = 2000
        self.tiempo_acumulado_accidente = 0

        # Generación de vehículos
        self.intervalo_spawn = 200
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

    def construir_fases_nodos(self):
        """Asigna fases conflictivas a cada nodo basándose en sus calles entrantes."""
        for nid, nodo in self.nodos.items():
            entrantes = self.calles_por_destino.get(nid, [])
            nodo.construir_fases(entrantes)
            # Desfasar semáforos para evitar sincronización artificial
            if nodo.fases and len(nodo.fases) > 1:
                nodo.fase_activa = random.randint(0, len(nodo.fases) - 1)
                nodo.tiempo_en_fase = random.randint(0, 2000)

    def generar_vehiculos(self, dt):
        self.tiempo_acumulado_spawn += dt
        if self.tiempo_acumulado_spawn >= self.intervalo_spawn:
            self.tiempo_acumulado_spawn = 0
            calles_disponibles = [c for c in self.calles if len(c.vehiculos) < c.capacidad]
            if calles_disponibles:
                calle = random.choice(calles_disponibles)
                calle.vehiculos.append(0.0)

    def mover_vehiculos(self, dt):
        velocidad = dt / 2000.0

        for calle in self.calles:
            if not calle.vehiculos:
                continue

            factor_accidente = 0.3 if calle.accidente_activo else 1.0
            vel = velocidad * factor_accidente

            nuevos = []
            for progreso in calle.vehiculos:
                progreso += vel
                if progreso >= 1.0:
                    # Verificar si esta calle tiene verde en el nodo destino
                    tiene_verde = calle.destino.calle_tiene_verde(calle)
                    if tiene_verde:
                        # Redirigir a calle saliente
                        salidas = self.calles_por_origen.get(calle.destino.id_nodo, [])
                        salidas_ok = [s for s in salidas
                                      if len(s.vehiculos) < s.capacidad
                                      and s.destino != calle.origen]
                        if salidas_ok:
                            siguiente = random.choice(salidas_ok)
                            siguiente.vehiculos.append(0.0)
                        # Vehículo sale de esta calle
                    else:
                        # Rojo: espera al final
                        nuevos.append(min(progreso, 0.99))
                else:
                    nuevos.append(progreso)
            calle.vehiculos = nuevos

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

    def step(self, dt):
        self.generar_vehiculos(dt)
        self.mover_vehiculos(dt)
        self.inyectar_accidentes(dt)
        for nodo in self.nodos.values():
            nodo.actualizar(dt)


# --- RENDERIZADO VISUAL ---

def ejecutar_visualizacion():
    pygame.init()
    pantalla = pygame.display.set_mode((800, 650))
    pygame.display.set_caption("Simulación Net Interactions - SOTL")
    reloj = pygame.time.Clock()
    fuente = pygame.font.SysFont(None, 16)
    fuente_info = pygame.font.SysFont(None, 14)

    sim = SimulacionSOTL("data/interactions.json")

    corriendo = True
    while corriendo:
        dt = reloj.tick(60)

        for evento in pygame.event.get():
            if evento.type == pygame.QUIT:
                corriendo = False

        sim.step(dt)

        pantalla.fill((30, 30, 30))

        # Dibujar calles con color según estado de verde/rojo
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

            # Dibujar vehículos
            for progreso in calle.vehiculos:
                vx = calle.origen.x + (calle.destino.x - calle.origen.x) * progreso
                vy = calle.origen.y + (calle.destino.y - calle.origen.y) * progreso
                # Amarillo si avanza, naranja si espera
                vc = (255, 160, 30) if progreso >= 0.95 else (255, 220, 50)
                pygame.draw.circle(pantalla, vc, (int(vx), int(vy)), 3)

        # Dibujar nodos con indicador de fase
        for nodo in sim.nodos.values():
            if len(nodo.fases) <= 1:
                # Nodo con una sola fase: siempre verde
                pygame.draw.circle(pantalla, (0, 180, 0), (nodo.x, nodo.y), 10)
            else:
                # Dibujar dos semicírculos: fase H y fase V
                fase_h_activa = nodo.fase_activa == 0
                # Semicírculo izquierdo (horizontal)
                rect = pygame.Rect(nodo.x - 10, nodo.y - 10, 20, 20)
                color_h = (0, 200, 0) if fase_h_activa else (200, 0, 0)
                color_v = (200, 0, 0) if fase_h_activa else (0, 200, 0)
                pygame.draw.circle(pantalla, color_h, (nodo.x - 5, nodo.y), 7)
                pygame.draw.circle(pantalla, color_v, (nodo.x + 5, nodo.y), 7)

            pygame.draw.circle(pantalla, (255, 255, 255), (nodo.x, nodo.y), 11, 1)
            etiqueta = fuente.render(nodo.id_nodo, True, (220, 220, 220))
            pantalla.blit(etiqueta, (nodo.x - etiqueta.get_width() // 2, nodo.y - 22))

        # Info
        total_v = sum(len(c.vehiculos) for c in sim.calles)
        info = fuente_info.render(f"Vehículos: {total_v}  |  Nodos: {len(sim.nodos)}", True, (150, 150, 150))
        pantalla.blit(info, (10, 635))

        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    ejecutar_visualizacion()
