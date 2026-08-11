import "./styles/styles.css";
import "./styles/contract.css";
import "./styles/architecture.css";
import { init } from "./bootstrap";
import { showToast } from "./shell/toast";

init().catch((error: unknown) => {
  const message = error instanceof Error ? error.message : String(error);
  showToast(String(message || error), "error");
});
