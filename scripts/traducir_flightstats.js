// Pone en castellano la ficha de FlightStats (Historical Flight Status) antes de la captura,
// como cuando la asesora le da a "Traducir" en Chrome. Solo cambia textos de la página
// abierta (no toca nada en FlightStats). Devuelve cuántos textos tradujo y los que quedan
// en inglés en la parte de arriba, para revisarlos.
(() => {
  const MES = {Jan:'ene',Feb:'feb',Mar:'mar',Apr:'abr',May:'may',Jun:'jun',Jul:'jul',Aug:'ago',Sep:'sept',Oct:'oct',Nov:'nov',Dec:'dic'};
  const FIJO = {
    'Departure':'Salida','Arrival':'Llegada','Scheduled':'Programada','Actual':'Real',
    'Estimated':'Estimada','Flight Gate Times':'Horarios de puerta','Flight Runway Times':'Horarios de pista',
    'Terminal':'Terminal','Gate':'Puerta','Baggage Claim':'Recogida de equipaje','Baggage':'Equipaje',
    'Craft Type':'Tipo de avión','Aircraft':'Avión','Equipment':'Avión','Flight Time':'Tiempo de vuelo',
    'Tail Number':'Matrícula','Flight Notes':'Notas del vuelo','Flight Timeline':'Cronología del vuelo',
    'Arrived':'Llegó','Landed':'Aterrizó','Departed':'Despegó','On time':'A tiempo','On Time':'A tiempo',
    'Early':'Adelantado','Cancelled':'Cancelado','Canceled':'Cancelado','Diverted':'Desviado',
    'Redirected':'Redirigido','Unknown':'Desconocido','Status':'Estado','Flight Status':'Estado del vuelo',
    'Historical Flight Status':'Estado histórico del vuelo','Codeshares':'Códigos compartidos',
    'Flights':'Vuelos','Airports':'Aeropuertos','On-Time Performance':'Puntualidad','Resources':'Recursos',
    'Follow us on':'Síguenos en','Logout':'Cerrar sesión','Login':'Iniciar sesión','My FlightStats':'Mi FlightStats',
    'Track Flight':'Seguir vuelo','Search':'Buscar','Date':'Fecha','Time':'Hora','Event':'Evento',
    'Flight':'Vuelo','Airline':'Aerolínea','Route':'Ruta','Distance':'Distancia','Delay':'Retraso',
    'Departure Delay':'Retraso de salida','Arrival Delay':'Retraso de llegada','Runway Delay':'Retraso en pista',
  };
  const dur = s => s.replace(/(\d+)\s*mins?\b/g, '$1 min').replace(/(\d+)\s*hrs?\b/g, '$1 h');
  const REGLAS = [
    [/^\(([A-Z0-9]{2,3})\)\s+(.+?)\s+(\S+)\s+Historical Flight Status$/, (m,a,b,c) => `Estado histórico del vuelo (${a}) ${b} ${c}`],
    [/^Delayed by\s*(.*)$/i, (m,x) => `Retrasado ${x}`.trim()],
    [/^Total Departure Delay:?\s*(.*)$/, (m,x) => `Retraso total de salida: ${dur(x)}`.trim()],
    [/^Total Arrival Delay:?\s*(.*)$/, (m,x) => `Retraso total de llegada: ${dur(x)}`.trim()],
    [/^Runway Delay:?\s*(.*)$/, (m,x) => `Retraso en pista: ${dur(x)}`.trim()],
    [/^Operated by (.+) on behalf of (.+)$/, (m,a,b) => `Operado por ${a} en nombre de ${b}`],
    [/^Also marketed as (.+)$/, (m,a) => `También comercializado como ${a}`],
    [/^(.+?) (?:International )?Airport(,.*)?$/, (m,a,r) => `Aeropuerto ${/International Airport/.test(m) ? 'Internacional ' : ''}${a}${r || ''}`],
    [/^(\d{1,2})-(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)-(\d{4})$/, (m,d,mm,y) => `${d}-${MES[mm]}-${y}`],
    [/^(\d+\s*h\s*)?\d+\s*mins?$/, m => dur(m)],
  ];
  const traducir = t => {
    if (t.includes(' | ')) return t.split(' | ').map(traducir).join(' | ');
    if (FIJO[t]) return FIJO[t];
    for (const [re, f] of REGLAS) { const m = t.match(re); if (m) return f(...m); }
    return null;
  };
  let n = 0;
  const quedan = new Set();
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
    acceptNode: x => /^(SCRIPT|STYLE|NOSCRIPT)$/.test(x.parentNode.nodeName) ? 2 : 1 });
  const nodos = [];
  while (w.nextNode()) nodos.push(w.currentNode);
  for (const nodo of nodos) {
    const v = nodo.nodeValue, t = v.trim();
    if (!t) continue;
    const es = traducir(t);
    if (es) { if (es !== t) { nodo.nodeValue = v.replace(t, es); n++; } continue; }
    if (/^[A-Z0-9 ()-]+$/.test(t)) continue;
    const r = nodo.parentNode.getBoundingClientRect && nodo.parentNode.getBoundingClientRect();
    if (/[a-z]{3}/i.test(t) && r && r.top < 900 && r.width > 0) quedan.add(t.slice(0, 60));
  }
  document.documentElement.lang = 'es';
  document.title = document.title.replace('Historical Flight Status', 'Estado histórico del vuelo');
  return {traducidos: n, quedan_en_ingles: [...quedan].slice(0, 40)};
})()
