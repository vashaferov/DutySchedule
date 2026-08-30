-- Добавляем колонки updated_at
ALTER TABLE duty_dates ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE duty_assignments ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE repertoire ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- Функция для обновления updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Триггеры на обновление
DROP TRIGGER IF EXISTS update_duty_dates_updated_at ON duty_dates;
CREATE TRIGGER update_duty_dates_updated_at
BEFORE UPDATE ON duty_dates
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_duty_assignments_updated_at ON duty_assignments;
CREATE TRIGGER update_duty_assignments_updated_at
BEFORE UPDATE ON duty_assignments
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_repertoire_updated_at ON repertoire;
CREATE TRIGGER update_repertoire_updated_at
BEFORE UPDATE ON repertoire
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

-- Таблица метаданных синхронизации
CREATE TABLE IF NOT EXISTS sync_metadata (
    key VARCHAR(50) PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Вставляем начальную запись (если ещё нет)
INSERT INTO sync_metadata (key, value) 
SELECT 'last_sync', to_char(CURRENT_TIMESTAMP, 'YYYY-MM-DD HH24:MI:SS')
WHERE NOT EXISTS (SELECT 1 FROM sync_metadata WHERE key = 'last_sync');