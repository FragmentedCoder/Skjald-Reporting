// The expression worker: evaluates template expressions off the page's thread, so a
// slow one can't freeze the builder or the form. client.ts stops it when a batch
// runs over its time limit and starts a fresh one.

import { JobRunner, type Request } from "./jobs";

const runner = new JobRunner();

self.onmessage = (event: MessageEvent<Request>) => {
  self.postMessage(runner.handle(event.data));
};
