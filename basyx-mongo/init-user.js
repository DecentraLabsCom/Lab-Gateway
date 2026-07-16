// Creates the least-privilege BaSyx application user during first startup.
// The official Mongo image runs init scripts before enabling authentication;
// credentials are supplied only through the container environment.
(function () {
    const username = process.env.BASYX_MONGO_USER;
    const password = process.env.BASYX_MONGO_PASSWORD;
    const rootPassword = process.env.MONGO_INITDB_ROOT_PASSWORD;
    if (!rootPassword || ["change_me", "changeme", "password", "test"].includes(rootPassword.toLowerCase())) {
        throw new Error("MONGO_INITDB_ROOT_PASSWORD must be a non-default secret");
    }
    if (!username || !password || ["change_me", "changeme", "password", "test"].includes(password.toLowerCase())) {
        throw new Error("BASYX_MONGO_USER and BASYX_MONGO_PASSWORD must be configured");
    }

    const database = db.getSiblingDB("basyx");
    if (database.getUser(username)) {
        print("BaSyx Mongo application user already exists");
        return;
    }
    database.createUser({
        user: username,
        pwd: password,
        roles: [{ role: "readWrite", db: "basyx" }],
    });
    print("Created least-privilege BaSyx Mongo application user");
})();
