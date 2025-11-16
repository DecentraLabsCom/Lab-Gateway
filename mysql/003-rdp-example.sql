-- Create a new RDP connection in Guacamole
INSERT INTO guacamole_connection (connection_name, protocol, max_connections, max_connections_per_user)
VALUES ('RDP-Example', 'rdp', 10, 5);

-- Get the ID of the newly created connection
SET @connection_id = LAST_INSERT_ID();

-- RDP connection parameters
INSERT INTO guacamole_connection_parameter (connection_id, parameter_name, parameter_value) VALUES
(@connection_id, 'hostname', '192.168.104.202'),
(@connection_id, 'port', '3389'),
(@connection_id, 'username', 'user123'),
(@connection_id, 'password', 'password123'),
(@connection_id, 'ignore-cert', 'true');


-- Get the entity_id of the user guacadmin
SET @entity_id = (
  SELECT entity_id
  FROM guacamole_entity
  WHERE name = 'guacadmin' AND type = 'USER'
);

-- Grant read permission on the connection to the user
INSERT INTO guacamole_connection_permission (entity_id, connection_id, permission)
VALUES (@entity_id, @connection_id, 'READ');