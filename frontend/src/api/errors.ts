export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

export function describeError(error: Error): string {
  if (!(error instanceof ApiError)) return 'Нет связи с сервером. Проверьте интернет и повторите.';
  if (error.status === 401) return 'Откройте приложение из чата с ботом в MAX.';
  if (error.status === 403) return 'Приложение доступно только владельцу сети.';
  if (error.status === 404) return 'Данные не найдены. Возможно, их удалили.';
  if (error.status === 409) return error.message || 'Данные успели измениться. Обновите экран.';
  if (error.status === 501) return 'Этот раздел ещё не готов на сервере.';
  if (error.status >= 500) return 'Сервер не отвечает. Попробуйте ещё раз.';
  return error.message || 'Не удалось выполнить действие.';
}
