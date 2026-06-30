
export function showAlert(msg: string): void {
  try {
    window.electronAPI.showAlert(msg);
  } catch {
    alert(msg);
  }
}
