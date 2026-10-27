// Files the frontend shares with the server, in shared/ at the top of the repository:
// the one place they're read from, so the relative path appears once. The image build
// copies shared/ beside the frontend (deploy/caddy.Dockerfile).

export { default as celFunctions } from "../../../shared/cel/functions.json";
export { default as contextNames } from "../../../shared/templates/names.json";
export { default as defaultStyle } from "../../../shared/styles/default.json";
export { default as sampleTemplate } from "../../../shared/templates/incident.json";
