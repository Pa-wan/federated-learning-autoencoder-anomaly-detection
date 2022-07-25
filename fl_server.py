import argparse
from collections import OrderedDict
from typing import Callable, Dict, Optional, Tuple, List

import flwr as fl
from flwr.common import Metrics
import numpy as np
import torch

from codes.data_loader import *
from codes.model_utils import *
from codes.evaluations.eval_utils import *

# pylint: disable=no-member
DEVICE = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
# pylint: enable=no-member

parser = argparse.ArgumentParser(description="Flower")
parser.add_argument(
    "--server_address",
    type=str,
    required=True,
    help=f"gRPC server address",
)
parser.add_argument(
    "--rounds",
    type=int,
    default=5,
    help="Number of rounds of federated learning (default: 1)",
)
parser.add_argument(
    "--min_sample_size",
    type=int,
    default=3,
    help="Minimum number of clients used for fit/evaluate (default: 2)",
)
parser.add_argument(
    "--min_num_clients",
    type=int,
    default=3,
    help="Minimum number of available clients required for sampling (default: 2)",
)
parser.add_argument(
    "--model",
    type=str,
    default="AE",
    help="model to train",
)
parser.add_argument(
    "--dataset",
    type=str,
    default="ENERGY",
    help="dataset to train and test",
)
parser.add_argument(
    "--num_workers",
    type=int,
    default=10,
    help="number of workers for dataset reading",
)
parser.add_argument("--pin_memory", action="store_true")
args = parser.parse_args()

def evaluate_config(rnd: int):
    """Return evaluation configuration dict for each round.
    Perform five local evaluation steps on each client (i.e., use five
    batches) during rounds one to three, then increase to ten local
    evaluation steps.
    """
    val_steps = 5 if rnd < 4 else 10
    return {"val_steps": val_steps}

def weighted_average(metrics: List[Tuple[int, Metrics]]) -> Metrics:
    print('=======> Metrics: ', metrics)
    # Multiply accuracy of each client by number of examples used
    accuracies = [num_examples * m["accuracy"] for num_examples, m in metrics]
    examples = [num_examples for num_examples, _ in metrics]
    # Aggregate and return custom metric (weighted average)
    return {"accuracy": sum(accuracies) / sum(examples)}

def main() -> None:
    """Start server and train five rounds."""
    print(args)

    assert (
        args.min_sample_size <= args.min_num_clients
    ), f"Num_clients shouldn't be lower than min_sample_size"

    # Configure logger
    fl.common.logger.configure("server")
    
    config = {
        "learning_rate": 0.0001,
        "weight_decay": 1e-6,
        "num_window": 10,
    }

    # Load evaluation data
    train_loader, test_loader, labels = load_dataset(args.dataset)
    model, optimizer, scheduler, _, _ = load_model(args.model, labels.shape[1], config)
    model_weights = [val.cpu().numpy() for _, val in model.state_dict().items()]
    
    # Create client_manager, strategy, and server
    client_manager = fl.server.SimpleClientManager()
    strategy = fl.server.strategy.FedAvg(
        fraction_fit=0.2,
        fraction_eval=0.2,
        min_fit_clients=args.min_sample_size,
        min_eval_clients=args.min_sample_size,
        min_available_clients=args.min_num_clients,
        eval_fn=get_eval_fn(model, optimizer, scheduler, train_loader, test_loader, labels),
        on_fit_config_fn=fit_config,
        on_evaluate_config_fn=evaluate_config,
        evaluate_metrics_aggregation_fn=weighted_average,
        initial_parameters=fl.common.weights_to_parameters(model_weights),
    )
    server = fl.server.Server(client_manager=client_manager, strategy=strategy)

    # Run server
    fl.server.start_server(
        server_address=args.server_address,
        server=server,
        config={"num_rounds": args.rounds},
    )


def fit_config(rnd: int) -> Dict[str, fl.common.Scalar]:
    """Return a configuration with static batch size and (local) epochs."""
    config = {
        "epoch_global": str(rnd),
        "epochs": str(5),
        "num_workers": str(args.num_workers),
        "pin_memory": str(args.pin_memory),
        "model": args.model,
        "dataset": args.dataset,
    }
    return config


def set_weights(model: torch.nn.ModuleList, weights: fl.common.Weights) -> None:
    """Set model weights from a list of NumPy ndarrays."""
    state_dict = OrderedDict(
        {
            k: torch.tensor(np.atleast_1d(v))
            for k, v in zip(model.state_dict().keys(), weights)
        }
    )
    model.load_state_dict(state_dict, strict=True)


def get_eval_fn(
    model, optimizer, scheduler, train, test, labels
) -> Callable[[fl.common.Weights], Optional[Tuple[float, float]]]:
    def evaluate(weights: fl.common.Weights) -> Optional[Tuple[float, float]]:
        set_weights(model, weights); model.to(DEVICE)
        
        trainD, testD = next(iter(train)), next(iter(test))
        trainO, testO = trainD, testD
        
        if model.name == "AE":
            trainD, testD = convert_to_windows(trainD, model), convert_to_windows(testD, model)
    
        loss, _ = backprop(0, model, testD, testO, optimizer, scheduler, training=False)
        lossT, _ = backprop(0, model, trainD, trainO, optimizer, scheduler, training=False)
        
        lossTfinal, lossFinal = np.mean(lossT, axis=1), np.mean(loss, axis=1)
        labelsFinal = (np.sum(labels, axis=1) >= 1) + 0
        
        result, _ = pot_eval(lossTfinal, lossFinal, labelsFinal)
        
        accuracy = (result['TP'] + result['TN']) / (result['TP'] + result['TN'] + result['FP'] + result['FN'])
        ls = np.sum(lossFinal)
        
        print(result)
        
        print("++++++++> Loss: ", ls)
        print("++++++++> Accuracy: ", accuracy)
        return ls, {"accuracy": accuracy}
    return evaluate


if __name__ == "__main__":
    main()