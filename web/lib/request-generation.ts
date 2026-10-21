/** Invalidate in-flight responses before React commits a new search state. */
export class RequestGeneration {
  private generation = 0;

  current() { return this.generation; }
  invalidate() { this.generation += 1; }
  isCurrent(value: number) { return value === this.generation; }
}
