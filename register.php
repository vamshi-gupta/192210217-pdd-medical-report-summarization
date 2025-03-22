<?php
include('db.php'); // Ensure db.php contains proper database connection

header('Content-Type: application/json');

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    // Check if required fields are set
    if (isset($_POST['name'], $_POST['email'], $_POST['phone'], $_POST['address'], $_POST['password'])) {
        
        // Sanitize input values
        $name = htmlspecialchars(trim($_POST['name']));
        $email = filter_var(trim($_POST['email']), FILTER_SANITIZE_EMAIL);
        $phone = htmlspecialchars(trim($_POST['phone']));
        $address = htmlspecialchars(trim($_POST['address']));
        $password = password_hash(trim($_POST['password']), PASSWORD_BCRYPT); // Hash password securely

        // Check if email already exists
        $check_stmt = $conn->prepare("SELECT id FROM users WHERE email = ?");
        $check_stmt->bind_param("s", $email);
        $check_stmt->execute();
        $check_stmt->store_result();
        
        if ($check_stmt->num_rows > 0) {
            echo json_encode(["message" => "Email already exists. Please use a different email."]);
            exit();
        }
        $check_stmt->close();

        // Prepare and execute SQL statement
        $stmt = $conn->prepare("INSERT INTO users (name, email, phone, address, password) VALUES (?, ?, ?, ?, ?)");
        if ($stmt === false) {
            echo json_encode(["message" => "Database error: Unable to prepare statement."]);
            exit();
        }

        $stmt->bind_param("sssss", $name, $email, $phone, $address, $password);

        if ($stmt->execute()) {
            $last_id = $stmt->insert_id;
            $stmt->close();

            // Retrieve the inserted data
            $result = $conn->query("SELECT id, name, email, phone, address FROM users WHERE id = $last_id");

            if ($result && $row = $result->fetch_assoc()) {
                echo json_encode(["message" => "Registration successful.", "data" => $row]);
            } else {
                echo json_encode(["message" => "Error fetching inserted data."]);
            }
        } else {
            echo json_encode(["message" => "Error: " . $stmt->error]);
        }
    } else {
        echo json_encode(["message" => "Invalid input or missing required fields."]);
    }
} else {
    echo json_encode(["message" => "Invalid request method."]);
}
?>
