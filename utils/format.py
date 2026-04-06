def format_value(value, format_type: str) -> str:
  """Değerleri kullanıcı dostu formatta döndür"""
  if value == 'Bilgi Yok' or value is None:
      return 'Bilgi Yok'
  if format_type == 'percent':
      return f"{value:.2%}"
  elif format_type == 'number':
      return f"{value:,.2f}"
  elif format_type == 'integer':
      return f"{value:,}"
  return str(value)