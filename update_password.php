<?php
session_start();
include('db.php'); // Ensure database connection

header('Content-Type: application/json');

if (!isset($_SESSION['user_id'])) {
    echo json_encode(["status" => "error", "message" => "User not logged in"]);
    exit();
}

$user_id = $_SESSION['user_id'];
$old_password = $_POST['old_password'];
$new_password = $_POST['new_password'];
$confirm_password = $_POST['confirm_password'];

// Validate New Password and Confirm Password
if ($new_password !== $confirm_password) {
    echo json_encode(["status" => "error", "message" => "New passwords do not match"]);
    exit();
}

// Check if the Old Password is Correct
$stmt = $conn->prepare("SELECT password FROM users WHERE id = ?");
$stmt->bind_param("i", $user_id);
$stmt->execute();
$result = $stmt->get_result();

if ($result->num_rows == 1) {
    $row = $result->fetch_assoc();
    
    if (!password_verify($old_password, $row['password'])) {
        echo json_encode(["status" => "error", "message" => "Old password is incorrect"]);
        exit();
    }
} else {
    echo json_encode(["status" => "error", "message" => "User not found"]);
    exit();
}

// Hash the New Password and Update It
$hashed_password = password_hash($new_password, PASSWORD_DEFAULT);
$updateStmt = $conn->prepare("UPDATE users SET password = ? WHERE id = ?");
$updateStmt->bind_param("si", $hashed_password, $user_id);

if ($updateStmt->execute()) {
    echo json_encode(["status" => "success", "message" => "Password updated successfully!"]);
} else {
    echo json_encode(["status" => "error", "message" => "Password update failed"]);
}

$stmt->close();
$updateStmt->close();
$conn->close();
?>
