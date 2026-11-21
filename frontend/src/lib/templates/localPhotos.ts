// Photos chosen in "Try it" stay in the browser: nothing is uploaded until there are
// reports. Each is kept here under a name of its own, which the answers hold in its
// place, and is drawn on a canvas where it prints. (Not shown as an image from a blob:
// or data: address: the page's Content-Security-Policy takes images from Skjald itself
// only, and stays that strict.)

export const LOCAL_PHOTO = "local-photo:";

const photos = new Map<string, File>();
let count = 0;

/** Keeps a chosen photo, and gives the name the answer holds for it. */
export function keepPhoto(file: File): string {
  const name = `${LOCAL_PHOTO}${++count}:${file.name}`;
  photos.set(name, file);
  return name;
}

export const isLocalPhoto = (address: string | null | undefined): address is string => Boolean(address?.startsWith(LOCAL_PHOTO));

/** Draws a kept photo on a canvas, at no more than twice the width it's shown at. */
export function drawPhoto(canvas: HTMLCanvasElement, name: string) {
  let wanted = name;
  const draw = async (which: string) => {
    const file = photos.get(which);
    if (!file) return;
    try {
      const bitmap = await createImageBitmap(file);
      if (which !== wanted) return bitmap.close();
      const scale = Math.min(1, 1600 / bitmap.width);
      canvas.width = Math.max(1, Math.round(bitmap.width * scale));
      canvas.height = Math.max(1, Math.round(bitmap.height * scale));
      canvas.getContext("2d")?.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
      bitmap.close();
    } catch {
      // Not a picture the browser can read: the canvas stays empty.
    }
  };
  void draw(name);
  return {
    update(next: string) {
      wanted = next;
      void draw(next);
    },
  };
}
