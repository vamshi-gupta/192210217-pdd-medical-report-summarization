<?php
session_start();
include('db.php');

header('Content-Type: application/json');

if (!isset($_SESSION['user_id'])) {
    echo json_encode(["status" => "error", "message" => "User not logged in"]);
    exit();
}

if (isset($_GET['id'])) {
    $summary_id = intval($_GET['id']);
    $user_id = $_SESSION['user_id'];

    // Ensure the user can only delete their own summaries
    $stmt = $conn->prepare("DELETE FROM summaries WHERE id = ? AND user_id = ?");
    $stmt->bind_param("ii", $summary_id, $user_id);

    if ($stmt->execute() && $stmt->affected_rows > 0) {
        echo json_encode(["status" => "success", "message" => "Summary deleted successfully."]);
    } else {
        echo json_encode(["status" => "error", "message" => "Error deleting summary."]);
    }
    $stmt->close();
} else {
    echo json_encode(["status" => "error", "message" => "Invalid request."]);
}
?>
