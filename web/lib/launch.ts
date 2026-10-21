/** Read at request time so one image can be promoted without rebuilding. */
export function isLaunched(): boolean {
  return Reflect.get(process.env, "OPENJOBS_PUBLIC_LAUNCH_ENABLED") === "1";
}
