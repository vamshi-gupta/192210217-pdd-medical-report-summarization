<?php
session_start();
include('db.php'); // Ensure db.php contains proper database connection

header('Content-Type: application/json');

if (!isset($_SESSION['user_id'])) {
    echo json_encode(["status" => "error", "message" => "User not logged in"]);
    exit();
}

$user_id = $_SESSION['user_id'];

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    // Check if required fields are set
    if (isset($_POST['name'], $_POST['email'], $_POST['phone'], $_POST['address'], $_POST['gender'])) {
        
        // Sanitize input values
        $name = htmlspecialchars(trim($_POST['name']));
        $email = filter_var(trim($_POST['email']), FILTER_SANITIZE_EMAIL);
        $phone = htmlspecialchars(trim($_POST['phone']));
        $address = htmlspecialchars(trim($_POST['address']));
        $gender = htmlspecialchars(trim($_POST['gender']));

        // Check if profile exists for the user
        $stmt = $conn->prepare("SELECT id FROM profile WHERE user_id = ?");
        $stmt->bind_param("i", $user_id);
        $stmt->execute();
        $stmt->store_result();
        $profile_exists = $stmt->num_rows > 0;
        $stmt->close();

        if ($profile_exists) {
            // Update existing profile
            $stmt = $conn->prepare("UPDATE profile SET name=?, email=?, phone=?, address=?, gender=? WHERE user_id=?");
            $stmt->bind_param("sssssi", $name, $email, $phone, $address, $gender, $user_id);
        } else {
            // Insert new profile
            $stmt = $conn->prepare("INSERT INTO profile (user_id, name, email, phone, address, gender) VALUES (?, ?, ?, ?, ?, ?)");
            $stmt->bind_param("isssss", $user_id, $name, $email, $phone, $address, $gender);
        }

        if ($stmt->execute()) {
            echo json_encode(["status" => "success", "message" => "Profile updated successfully."]);
        } else {
            echo json_encode(["status" => "error", "message" => "Database error: " . $stmt->error]);
        }
        $stmt->close();
    } else {
        echo json_encode(["status" => "error", "message" => "Missing required fields."]);
    }
} else {
    // Fetch user profile if exists
    $stmt = $conn->prepare("SELECT name, email, phone, address, gender FROM profile WHERE user_id = ?");
    $stmt->bind_param("i", $user_id);
    $stmt->execute();
    $result = $stmt->get_result();

    if ($result->num_rows > 0) {
        $profile = $result->fetch_assoc();
        echo json_encode(["status" => "success", "data" => $profile]);
    } else {
        echo json_encode(["status" => "error", "message" => "No profile found"]);
    }
    $stmt->close();
}
?>
