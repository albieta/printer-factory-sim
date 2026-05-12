const SIMULATION_UPDATED_EVENT = 'simulation-updated';

export const announceSimulationUpdate = () => {
  window.dispatchEvent(new Event(SIMULATION_UPDATED_EVENT));
};

export const onSimulationUpdate = (listener: () => void) => {
  window.addEventListener(SIMULATION_UPDATED_EVENT, listener);
  return () => window.removeEventListener(SIMULATION_UPDATED_EVENT, listener);
};
