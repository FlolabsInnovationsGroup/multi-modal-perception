import type { Plugin } from "vite";
import { handlePelApiRequest } from "./pel-api";
import { loadPelEnv } from "./load-pel-env";

export function pelApiPlugin(): Plugin {
  return {
    name: "pel-api",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const env = loadPelEnv(server.config.root, server.config.mode);
        void handlePelApiRequest(req, res, env).then((handled) => {
          if (!handled) next();
        });
      });
    },
    configurePreviewServer(server) {
      server.middlewares.use((req, res, next) => {
        const env = loadPelEnv(server.config.root, server.config.mode);
        void handlePelApiRequest(req, res, env).then((handled) => {
          if (!handled) next();
        });
      });
    },
  };
}
