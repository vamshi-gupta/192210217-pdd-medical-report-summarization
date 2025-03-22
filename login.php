<?php
session_start();
include('db.php'); // Ensure db.php contains the database connection

header('Content-Type: application/json');

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    if (isset($_POST['email'], $_POST['password'])) {
        $email = trim($_POST['email']);
        $password = trim($_POST['password']);

        // Prepare statement to fetch user details
        $stmt = $conn->prepare("SELECT id, name, email, phone, password FROM users WHERE email = ?");
        $stmt->bind_param("s", $email);
        $stmt->execute();
        $result = $stmt->get_result();

        if ($row = $result->fetch_assoc()) {
            // Verify the password (assuming password is hashed in the database)
            if (password_verify($password, $row['password'])) {
                $_SESSION['user_id'] = $row['id'];
                $_SESSION['email'] = $email;
                $_SESSION['name'] = $row['name'];

                echo json_encode([
                    "status" => "success",
                    "message" => "Login successful",
                    "redirect" => "home.html",
                    "data" => [
                        "id" => $row['id'],
                        "name" => $row['name'],
                        "email" => $row['email'],
                        "phone" => $row['phone']
                    ]
                ]);
                exit;
            }
        }
        $stmt->close();

        // If no match is found
        echo json_encode(["status" => "error", "message" => "Invalid email or password"]);
    } else {
        echo json_encode(["status" => "error", "message" => "Missing email or password"]);
    }
} else {
    echo json_encode(["status" => "error", "message" => "Invalid request method"]);
}

$conn->close();
?>
