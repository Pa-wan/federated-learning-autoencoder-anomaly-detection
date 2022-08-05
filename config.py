best_configs = {}
num_epochs = 100
lr = 1e-3

def get_best_config(algo_name):
    best_configs["USAD"] = {
        "num_epochs": 10,
        "num_hidden": 16,
        "latent": 5,
        "learning_rate": 0.0001,
        "weight_decay": 1e-5,
        "num_window": 10,
    }
    
    best_configs["AE"] = {
        "num_epochs": 15,
        "learning_rate": 0.0001,
        "weight_decay": 1e-5,
        "num_window": 5,
    }
    
    best_configs["LSTM_AD"] = {
        "beta": 0.01,
        "batch_size": 50,
        "embedding_dim": 16,
        "num_epochs": 5,
        "num_hidden": 32,
        "learning_rate": 0.0001,
        "layers": 3,
        "weight_decay": 1e-5,
    }
    
    best_configs["LSTM_Univariate"] = {
        "beta": 0.01,
        "batch_size": 50,
        "embedding_dim": 16,
        "num_epochs": 1,
        "num_hidden": 32,
        "learning_rate": 0.0001,
        "layers": 3,
        "weight_decay": 1e-5,
    }

    return best_configs[algo_name]