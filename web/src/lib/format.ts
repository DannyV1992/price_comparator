const colones = new Intl.NumberFormat("es-CR", { style: "currency", currency: "CRC", maximumFractionDigits: 0 });

export const formatPrice = (value: number) => colones.format(value);
