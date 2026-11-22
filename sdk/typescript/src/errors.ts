export class CbysError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = new.target.name;
  }
}

export class CbysHttpError extends CbysError {
  constructor(
    public readonly status: number,
    message: string,
    public readonly url: string,
    options?: ErrorOptions,
  ) {
    super(message, options);
  }
}

export class CbysBadRequestError extends CbysHttpError {
  constructor(message: string, url: string) {
    super(400, message, url);
  }
}

export class CbysNotFoundError extends CbysHttpError {
  constructor(message: string, url: string) {
    super(404, message, url);
  }
}

export class CbysNetworkError extends CbysError {
  constructor(public readonly url: string, cause: unknown) {
    super(`Network request failed for ${url}`, { cause });
  }
}

export class CbysTimeoutError extends CbysError {
  constructor(public readonly url: string, public readonly timeoutMs: number) {
    super(`Request timed out after ${timeoutMs} ms for ${url}`);
  }
}

export class CbysMixedUnitError extends CbysError {
  constructor(firstUnit: string, secondUnit: string) {
    super(`Cannot compare rates in ${firstUnit} and ${secondUnit}`);
  }
}

export class CbysMixedKindError extends CbysError {
  constructor(firstKind: string, secondKind: string) {
    super(`Cannot compare ${firstKind} and ${secondKind}`);
  }
}

export class CbysFixtureMissingError extends CbysError {
  constructor(public readonly key: string, options?: ErrorOptions) {
    super(`Request is not in fixtures: ${key}`, options);
  }
}
